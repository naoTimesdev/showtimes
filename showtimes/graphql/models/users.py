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

from dataclasses import dataclass
from typing import Optional, Type, cast
from uuid import UUID

import strawberry as gql
from beanie import PydanticObjectId

from showtimes.models.database import ShowtimesUser, ShowtimesUserDiscord
from showtimes.models.session import UserSession
from showtimes.utils import make_uuid

from .common import ImageMetadataGQL, IntegrationGQL
from .enums import UserTypeGQL

__all__ = ("UserGQL",)


@dataclass
class DiscordMetadata:
    id: str
    name: str
    access_token: str
    refresh_token: str
    expires_at: float

    def to_model(self) -> ShowtimesUserDiscord:
        return ShowtimesUserDiscord(
            id=self.id,
            name=self.name,
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            expires_at=self.expires_at,
        )


@gql.type(name="User", description="The user information")
class UserGQL:
    id: UUID = gql.field(description="The user ID")
    """The user ID"""
    username: str = gql.field(description="The user's username")
    """The user username"""
    privilege: UserTypeGQL = gql.field(description="The user's privilege level")
    """The user privilege level"""
    integrations: list[IntegrationGQL] = gql.field(description="The user's integrations information")
    """The user integrations information"""
    avatar: Optional[ImageMetadataGQL] = gql.field(description="The user's avatar URL")
    """The user avatar information"""

    user_id: gql.Private[str]  # ObjectId
    legacy_id: gql.Private[Optional[str]]  # ObjectId
    discord_meta: gql.Private[Optional[DiscordMetadata]]

    @classmethod
    def from_db(cls: Type[UserGQL], user: ShowtimesUser):
        legacy_id = None
        if user.legacy_info is not None:
            legacy_id = str(user.legacy_info.user_id)
            if user.legacy_info.migrated:
                legacy_id = None
        discord_meta: Optional[DiscordMetadata] = None
        if user.discord_meta:
            discord_meta = DiscordMetadata(
                id=user.discord_meta.id,
                name=user.discord_meta.name,
                access_token=user.discord_meta.access_token,
                refresh_token=user.discord_meta.refresh_token,
                expires_at=user.discord_meta.expires_at,
            )
        return cls(
            id=user.user_id,
            username=user.username,
            privilege=user.privilege,
            integrations=[IntegrationGQL.from_db(integration) for integration in user.integrations],
            avatar=ImageMetadataGQL.from_db(user.avatar, "users") if user.avatar else None,
            legacy_id=legacy_id,
            user_id=str(cast(PydanticObjectId, user.id)),
            discord_meta=discord_meta,
        )

    def to_session(self):
        return UserSession(
            session_id=make_uuid(),
            user_id=str(self.id),
            username=self.username,
            privilege=self.privilege,
            servers=[],
            object_id=self.user_id,
            discord_meta=self.discord_meta.to_model() if self.discord_meta else None,
        )
