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

from abc import ABC, abstractmethod
from fnmatch import fnmatchcase
from typing import Optional
from uuid import UUID

import orjson

from showtimes.models.session import UserSession

from ..redisdb import RedisDatabase
from .errors import BackendError

__all__ = (
    "InMemoryBackend",
    "RedisBackend",
)


class SessionBackend(ABC):
    """
    Session backend interface
    """

    @abstractmethod
    async def shutdown(self) -> None:
        """Close the connection to the database."""
        pass

    @abstractmethod
    async def create(self, session_id: UUID | str, data: UserSession) -> None:
        """
        Create new session data on the backend.

        Parameters
        ----------
        session_id : UUID
            The session ID to be created
        data : UserSession
            The user session information

        Raises
        ------
        BackendError
            If the session ID already exist on the backend
        """
        raise NotImplementedError

    @abstractmethod
    async def read(self, session_id: UUID | str) -> Optional[UserSession]:
        """
        Read or fetch session data from the backend.

        Parameters
        ----------
        session_id : UUID
            The session ID to be fetched

        Returns
        -------
        Optional[UserSession]
            The session if exist on the backend
        """
        raise NotImplementedError

    @abstractmethod
    async def update(self, session_id: UUID | str, data: UserSession) -> None:
        """
        Update session data on the backend.

        Parameters
        ----------
        session_id : UUID
            The session ID to be updated
        data : UserSession
            The user session information

        Raises
        ------
        BackendError
            If the session ID does not exist on the backend
        """
        raise NotImplementedError

    @abstractmethod
    async def delete(self, session_id: UUID | str) -> None:
        """
        Delete session data from the backend.

        Parameters
        ----------
        session_id : UUID
            The session ID to be deleted
        """
        raise NotImplementedError

    @abstractmethod
    async def bulk_delete(self, prefix: str):
        """
        Delete session data from the backend by prefix.

        Parameters
        ----------
        prefix : str
            The prefix to be deleted
        """
        raise NotImplementedError


class InMemoryBackend(SessionBackend):
    """Store session inside a memory dictionary."""

    def __init__(self) -> None:
        self.__SESSIONS: dict[UUID | str, UserSession] = {}

    async def shutdown(self) -> None:
        pass

    async def read(self, session_id: UUID | str) -> Optional[UserSession]:
        return self.__SESSIONS.get(session_id)

    async def create(self, session_id: UUID | str, data: UserSession) -> None:
        if self.__SESSIONS.get(session_id) is not None:
            raise BackendError("create can't overwrite an existing session")
        self.__SESSIONS[session_id] = data

    async def update(self, session_id: UUID | str, data: UserSession) -> None:
        if self.__SESSIONS.get(session_id) is None:
            raise BackendError("session does not exist, cannot update")
        self.__SESSIONS[session_id] = data

    async def delete(self, session_id: UUID | str) -> None:
        try:
            del self.__SESSIONS[session_id]
        except KeyError:
            pass

    async def bulk_delete(self, prefix: str):
        for session_id in list(self.__SESSIONS.keys()):
            if fnmatchcase(str(session_id), prefix):
                await self.delete(session_id)


class RedisBackend(SessionBackend):
    """Store session data in a redis database."""

    def __init__(
        self,
        host: str,
        port: int = 6379,
        password: Optional[str] = None,
        *,
        key_prefix: str = "showtimes:naotimes:session:",
    ):
        """Initialize a new redis database."""
        self._client = RedisDatabase(host, port, password)
        self._key_prefix = key_prefix

    async def shutdown(self) -> None:
        """Close the connection to the database."""
        await self._client.close()

    async def _before_operation(self):
        """Connect to the database before performing an operation."""
        if not self._client.is_connected:
            await self._client.connect()
            try:
                await self._client.get("pingpong")
            except ConnectionRefusedError as ce:
                raise BackendError("Connection to redis failed") from ce

    async def _check_key(self, session_id: UUID) -> bool:
        """Check if a key exists."""
        return await self._client.exists(self._key_prefix + str(session_id))

    def _dump_json(self, data: UserSession) -> str:
        return orjson.dumps(data.dict(), option=orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_SERIALIZE_UUID).decode()

    async def create(self, session_id: UUID, data: UserSession) -> None:
        await self._before_operation()
        if await self._check_key(session_id):
            raise BackendError("create can't overwrite an existing session")

        await self._client.set(self._key_prefix + str(session_id), self._dump_json(data.copy(deep=True)))

    async def read(self, session_id: UUID) -> Optional[UserSession]:
        await self._before_operation()
        data = await self._client.get(self._key_prefix + str(session_id))
        if not data:
            return
        return UserSession.parse_obj(data)

    async def update(self, session_id: UUID, data: UserSession) -> None:
        await self._before_operation()
        if not await self._check_key(session_id):
            raise BackendError("session does not exist, cannot update")

        await self._client.set(self._key_prefix + str(session_id), self._dump_json(data.copy(deep=True)))

    async def delete(self, session_id: UUID) -> None:
        await self._before_operation()
        await self._client.rm(self._key_prefix + str(session_id))

    async def bulk_delete(self, glob_keys: str):
        await self._before_operation()

        all_keys = await self._client.keys(self._key_prefix + glob_keys)
        for key in all_keys:
            await self._client.rm(key)
