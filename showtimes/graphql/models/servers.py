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

from typing import Type, cast

import strawberry as gql
from beanie.operators import In
from bson import ObjectId

from showtimes.models.database import (
    ShowProject,
    ShowtimesServer,
    ShowtimesTemporaryUser,
    ShowtimesUser,
    ShowtimesUserGroup,
)

from .common import ImageMetadataGQL
from .partials import PartialServerGQL
from .projects import ProjectGQL
from .users import UserGQL, UserTemporaryGQL

__all__ = ("ServerGQL",)


@gql.type(name="Server", description="The server information")
class ServerGQL(PartialServerGQL):
    @classmethod
    def from_db(cls: Type[ServerGQL], server: ShowtimesServer):
        return cls(
            id=server.server_id,
            name=server.name,
            avatar=ImageMetadataGQL.from_db(server.avatar) if server.avatar else None,
            server_id=str(server.id),
            project_links=[str(i.ref.id) for i in server.projects],
            owner_links=[str(i.ref.id) for i in server.owners],
        )

    @gql.field(description="List of projects that this server is linked to")
    async def projects(self) -> list[ProjectGQL]:
        object_ids = [ObjectId(i) for i in self.project_links]
        if not object_ids:
            return []
        results = await ShowProject.find(In(ShowProject.id, object_ids)).to_list()
        return [ProjectGQL.from_db(result) for result in results]

    @gql.field(description="List of owners that this server is linked to")
    async def owners(self) -> list[UserGQL | UserTemporaryGQL]:
        object_ids = [ObjectId(i) for i in self.owner_links]
        if not object_ids:
            return []
        owners = await ShowtimesUserGroup.find(In(ShowtimesUserGroup.id, object_ids), with_children=True).to_list()
        return [
            UserTemporaryGQL.from_db(cast(ShowtimesTemporaryUser, owner))
            if owner.is_temp_user()
            else UserGQL.from_db(cast(ShowtimesUser, owner))
            for owner in owners
        ]
