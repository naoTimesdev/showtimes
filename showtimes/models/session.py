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

from typing import Type
from uuid import UUID

from pydantic import BaseModel

from showtimes.utils import make_uuid

from .database import ShowtimesServer, ShowtimesUser, ShowtimesUserDiscord, UserType

__all__ = (
    "ServerSessionInfo",
    "UserSession",
)


class ServerSessionInfo(BaseModel):
    server_id: str
    name: str

    @classmethod
    def from_db(cls: Type["ServerSessionInfo"], server: ShowtimesServer):
        return cls(
            server_id=str(server.server_id),
            name=server.name,
        )


class UserSession(BaseModel):
    session_id: UUID
    user_id: str
    username: str
    privilege: UserType
    servers: list[ServerSessionInfo]
    object_id: str  # ObjectId, stringified
    discord_meta: ShowtimesUserDiscord | None = None
    active: ServerSessionInfo | None = None
    api_key: bool = False

    @classmethod
    def from_db(
        cls: Type["UserSession"], user: ShowtimesUser, servers: list[ShowtimesServer], is_api_key: bool = False
    ):
        return cls(
            session_id=make_uuid(),
            user_id=str(user.user_id),
            username=user.username,
            privilege=user.privilege,
            servers=[ServerSessionInfo.from_db(server) for server in servers],
            object_id=str(user.id),
            discord_meta=user.discord_meta,
            active=None,
            api_key=is_api_key,
        )

    @classmethod
    def create_master(cls: Type["UserSession"]):
        return cls(
            session_id=make_uuid(),
            user_id="-999MASTER",
            username="Master API",
            privilege=UserType.ADMIN,
            object_id="-999",
            servers=[],
            api_key=True,
        )
