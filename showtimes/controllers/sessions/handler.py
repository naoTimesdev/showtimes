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
from showtimes.tooling import get_env_config

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

        self._master_session = master_session

    def _make_key(self, data: UserSession):
        if data.api_key is not None:
            return f"|apimode|{data.api_key}"
        return str(data.session_id)

    async def set_session(self, data: UserSession, response: Optional[Response] = None):
        await self.backend.create(self._make_key(data), data)
        if response is not None:
            self.set_cookie(response, data.session_id)

    async def update_session(self, data: UserSession, response: Optional[Response] = None):
        await self.backend.update(self._make_key(data), data)
        if response is not None:
            self.set_cookie(response, data.session_id)

    async def set_or_update_session(self, data: UserSession, response: Optional[Response] = None):
        try:
            await self.update_session(data, response)
        except BackendError:
            await self.set_session(data, response)

    async def reset_user_api(self, api_key: str):
        await self.backend.delete(f"|apimode|{api_key}")

    async def reset_api(self):
        await self.backend.bulk_delete("|apimode|*")

    def set_cookie(self, response: Response, session_id: UUID):
        dumps = self.signer.dumps(session_id.hex)
        if isinstance(dumps, bytes):
            dumps = dumps.decode("utf-8")
        response.set_cookie(
            key=self.model.name,
            value=dumps,
            max_age=self.params.max_age,
            path=self.params.path,
            domain=self.params.domain,
            secure=self.params.secure,
            httponly=self.params.httponly,
            samesite=self.params.samesite.value,
        )

    async def remove_session(self, session_id: Union[str, UUID], response: Optional[Response] = None):
        as_uuid = UUID(session_id) if isinstance(session_id, str) else session_id
        await self.backend.delete(session_id=as_uuid)
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

    async def __call__(self, request: Union[Request, WebSocket]):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Token "):
            auth_header = auth_header[6:]
            master_key = get_env_config()["MASTER_KEY"]
            if auth_header == master_key:
                return self._master_session

            session_auth = await self.backend.read(f"|apimode|{auth_header}")
            if session_auth:
                return session_auth
            user_with_key = await ShowtimesUser.find_one(ShowtimesUser.api_key == auth_header)
            if user_with_key is None:
                raise SessionError(detail="Unknown API key", status_code=401)
            user_session = UserSession.from_db(user_with_key)
            await self.set_session(user_session)
            return user_session

        signed_session = request.cookies.get(self.model.name)
        if not signed_session:
            raise SessionError(detail="No session found", status_code=403)

        try:
            session = UUID(self.signer.loads(signed_session, max_age=self.params.max_age, return_timestamp=False))
        except (SignatureExpired, BadSignature) as exc:
            raise SessionError(detail="Session expired/invalid", status_code=401) from exc

        session_data = await self.backend.read(session)
        if not session_data:
            raise SessionError(detail="Session expired/invalid", status_code=401)
        return session_data


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


async def check_session(request: Union[Request, WebSocket]) -> UserSession:
    session_handler = get_session_handler()
    return await session_handler(request)


def is_master_session(session: UserSession) -> bool:
    MASTER_KEY = get_env_config()["MASTER_KEY"]
    if MASTER_KEY is None:
        raise RuntimeError("Master key is not set")
    return session.api_key is not None and session.api_key == MASTER_KEY
