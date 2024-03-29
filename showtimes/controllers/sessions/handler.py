"""
This file is part of Showtimes Backend Project.
Copyright 2022-present naoTimes Project <https://github.com/naoTimesdev/showtimes>.

Showtimes is free software: you can redistribute it and/or modify it under the terms of the
Affero GNU General Public License as published by the Free Software Foundation, either
version 3 of the License, or (at your option) any later version.

Showtimes is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the Affero GNU General Public License for more details.

You should have received a copy of the Affero GNU General Public License along with Showtimes.
If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Optional, Union
from uuid import UUID

from fastapi import Request, Response, WebSocket
from fastapi.openapi.models import APIKey, APIKeyIn
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from showtimes.models.database import ShowtimesUser
from showtimes.models.session import UserSession
from showtimes.tooling import get_env_config, get_logger

from .backend import InMemoryBackend, RedisBackend, SessionBackend
from .errors import BackendError, SessionError

__all__ = (
    "SameSiteEnum",
    "CookieParameters",
    "SessionHandler",
    "create_session_handler",
    "get_session_handler",
    "check_session",
    "is_master_session",
)
logger = get_logger("Showtimes.Session.Handler")


class SameSiteEnum(str, Enum):
    lax = "lax"
    strict = "strict"
    none = "none"


class CookieParameters(BaseModel):
    max_age: int = 14 * 24 * 60 * 60  # 14 days in seconds
    path: str = "/"
    domain: Optional[str] = None
    secure: bool = False
    httponly: bool = True
    samesite: SameSiteEnum = SameSiteEnum.lax


class UserSessionWithToken(UserSession):
    token: str

    @classmethod
    def from_session(cls, session: UserSession, token: str):
        return cls(
            session_id=session.session_id,
            user_id=session.user_id,
            username=session.username,
            privilege=session.privilege,
            object_id=session.object_id,
            discord_meta=session.discord_meta,
            active=session.active,
            api_key=session.api_key,
            token=token,
        )


class SessionHandler:
    def __init__(
        self,
        *,
        cookie_name: str,
        identifier: str,
        secret_key: str,
        params: CookieParameters,
        scheme_name: Optional[str] = None,
        backend: SessionBackend,
        master_session: UserSession,
    ):
        self.model: APIKey = APIKey(
            **{"in": APIKeyIn.cookie},  # type: ignore
            name=cookie_name,
        )
        self._identifier = identifier
        self.scheme_name = scheme_name or self.__class__.__name__
        self.signer = URLSafeTimedSerializer(secret_key, salt=cookie_name)
        self.params = params.copy(deep=True)

        self.backend = backend

        self._master_session = UserSessionWithToken.from_session(
            master_session,
            self.sign_session(master_session.session_id),
        )

    def _make_key(self, data: UserSession):
        if data.api_key is not None:
            return f"|apimode|{data.api_key}"
        return str(data.session_id)

    async def set_session(self, data: UserSession, response: Optional[Response] = None):
        await self.backend.create(
            self._make_key(data),
            UserSessionWithToken.from_session(
                data,
                self.sign_session(data.session_id),
            ),
        )
        if response is not None:
            self.set_cookie(response, data.session_id)

    async def update_session(self, data: UserSession, response: Optional[Response] = None):
        await self.backend.update(
            self._make_key(data),
            UserSessionWithToken.from_session(
                data,
                self.sign_session(data.session_id),
            ),
        )
        if response is not None:
            self.set_cookie(response, data.session_id)

    async def set_or_update_session(self, data: UserSession, response: Optional[Response] = None):
        try:
            logger.debug(f"Updating session: {data}")
            await self.update_session(data, response)
        except BackendError:
            logger.debug(f"Creating new session: {data}")
            await self.set_session(data, response)

    async def revoke_user_api(self, api_key: str):
        logger.debug(f"Revoking API access: {api_key}")
        await self.backend.delete(f"|apimode|{api_key}")

    async def reset_api(self):
        logger.debug("Revoking all API Access!")
        await self.backend.bulk_delete("|apimode|*")

    def sign_session(self, session_id: UUID) -> str:
        dumps = self.signer.dumps(session_id.hex)
        if isinstance(dumps, bytes):
            dumps = dumps.decode("utf-8")
        return dumps

    def _unsign_session(self, session: str) -> UUID:
        try:
            return UUID(self.signer.loads(session, max_age=self.params.max_age, return_timestamp=False))
        except (SignatureExpired, BadSignature) as exc:
            raise SessionError(detail="Session expired/invalid", status_code=401) from exc

    def set_cookie(self, response: Response, session_id: UUID):
        response.set_cookie(
            key=self.model.name,
            value=self.sign_session(session_id),
            max_age=self.params.max_age,
            path=self.params.path,
            domain=self.params.domain,
            secure=self.params.secure,
            httponly=self.params.httponly,
            samesite=self.params.samesite.value,
        )

    async def remove_session(self, session: UserSession, response: Optional[Response] = None):
        await self.backend.delete(self._make_key(session))
        if response is not None:
            self.remove_cookie(response)

    def remove_cookie(self, response: Response):
        if self.params.domain:
            response.delete_cookie(
                key=self.model.name,
                path=self.params.path,
                domain=self.params.domain,
            )
        else:
            response.delete_cookie(
                key=self.model.name,
                path=self.params.path,
            )

    @property
    def identifier(self) -> str:
        return self._identifier

    async def __call__(self, request: Union[Request, WebSocket]) -> UserSessionWithToken:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Token "):
            auth_header = auth_header[6:]
            logger.debug(f"Detected login via API key: {auth_header}")
            master_key = get_env_config()["MASTER_KEY"]
            if auth_header == master_key:
                logger.debug("API key is master key, returning master session")
                return self._master_session

            logger.debug(f"[{auth_header}] Checking if session is already active")
            session_auth = await self.backend.read(f"|apimode|{auth_header}")
            if session_auth:
                return UserSessionWithToken.from_session(session_auth, self.sign_session(session_auth.session_id))
            logger.debug(f"[{auth_header}] Checking if user exist with this API key")
            user_with_key = await ShowtimesUser.find_one(ShowtimesUser.api_key == auth_header)
            if user_with_key is None:
                raise SessionError(detail="Unknown API key", status_code=401)
            logger.debug(f"[{auth_header}] Creating new session for user")
            user_session = UserSession.from_db(user_with_key)
            await self.set_session(user_session)
            return UserSessionWithToken.from_session(user_session, self.sign_session(user_session.session_id))
        elif auth_header and auth_header.startswith("Bearer "):
            auth_header = auth_header[7:]
            logger.debug(f"Detected login via Bearer token: {auth_header}")
            session_auth = await self.backend.read(self._unsign_session(auth_header))
            if session_auth:
                return UserSessionWithToken.from_session(session_auth, self.sign_session(session_auth.session_id))
            raise SessionError(detail="Unknown Bearer token", status_code=401)

        logger.debug("Checking if session is already active")
        signed_session = request.cookies.get(self.model.name)
        if not signed_session:
            raise SessionError(detail="No session found", status_code=403)

        logger.debug(f"Checking session: {signed_session}")
        session = self._unsign_session(signed_session)

        logger.debug(f"Session is valid: {session}, checking backend")
        session_data = await self.backend.read(session)
        if not session_data:
            raise SessionError(detail="Session expired/invalid", status_code=401)
        logger.debug(f"Session is valid: {session}, returning session data")
        return UserSessionWithToken.from_session(session_data, signed_session)


_GLOBAL_SESSION_HANDLER: Optional[SessionHandler] = None


async def create_session_handler(
    secret_key: str,
    redis_host: Optional[str] = None,
    redis_port: int = 6379,
    redis_password: Optional[str] = None,
    max_age=7 * 24 * 60 * 60,
):
    global _GLOBAL_SESSION_HANDLER

    backend = InMemoryBackend()
    redis_host = redis_host.strip() if isinstance(redis_host, str) else redis_host
    if redis_host:
        backend = RedisBackend(redis_host, redis_port, redis_password)

    MASTER_KEY = get_env_config()["MASTER_KEY"]
    if MASTER_KEY is None:
        raise RuntimeError("Master key is not set")

    if _GLOBAL_SESSION_HANDLER is None:
        secure = os.getenv("NODE_ENV") == "production"
        cookie_params = CookieParameters(max_age=max_age, secure=secure)
        MASTER_SESSION = UserSession.create_master(MASTER_KEY)
        session = SessionHandler(
            cookie_name="naotimes|session",
            identifier="naotimes|ident",
            secret_key=secret_key,
            params=cookie_params,
            backend=backend,
            master_session=MASTER_SESSION,
        )
        # Reset all API sessions
        await session.reset_api()

        await session.set_session(MASTER_SESSION)

        _GLOBAL_SESSION_HANDLER = session


def get_session_handler() -> SessionHandler:
    global _GLOBAL_SESSION_HANDLER

    if _GLOBAL_SESSION_HANDLER is None:
        raise ValueError("Session not created, call create_session first")

    return _GLOBAL_SESSION_HANDLER


async def check_session(request: Union[Request, WebSocket]) -> UserSessionWithToken:
    session_handler = get_session_handler()
    return await session_handler(request)


def is_master_session(session: UserSession) -> bool:
    MASTER_KEY = get_env_config()["MASTER_KEY"]
    if MASTER_KEY is None:
        raise RuntimeError("Master key is not set")
    return session.api_key is not None and session.api_key == MASTER_KEY
