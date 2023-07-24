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

from typing import Optional, Type
from uuid import UUID

import strawberry as gql

from showtimes.models.database import (
    ShowProject,
    ShowtimesCollaboration,
    ShowtimesCollaborationInfo,
    ShowtimesCollaborationLinkSync,
    ShowtimesServer,
)

from .partials import PartialProjectGQL, PartialServerGQL

__all__ = (
    "ProjectCollabLinkGQL",
    "ProjectCollabConfirmationGQL",
)


@gql.type(name="ProjectCollabLink", description="A synchronization link to a project collab.")
class ProjectCollabLinkGQL:
    id: UUID = gql.field(description="The ID of this server.")
    project: UUID = gql.field(description="The ID of the project that is linked to this collab.")
    projects: list[UUID] = gql.field(description="The list of other projects that are linked to this collab.")
    servers: list[UUID] = gql.field(description="The list of servers that are linked to this collab.")
    internal_id: gql.Private[str]  # ObjectId

    @classmethod
    def from_db(
        cls: Type[ProjectCollabLinkGQL], server_id: UUID, project_id: UUID, link: ShowtimesCollaborationLinkSync
    ) -> ProjectCollabLinkGQL:
        return cls(
            id=server_id,
            project=project_id,
            projects=link.projects,
            servers=link.servers,
            internal_id=str(link.id),
        )


@gql.type(
    name="ProjectCollabConfirmationInfo",
    description="A confirmation link information of each link to a project collab.",
)
class ProjectCollabConfirmationInfoGQL:
    server_id: gql.Private[str]  # ObjectID
    project_id: gql.Private[str]  # ObjectID

    @gql.field(description="The partial project information")
    async def project(self) -> PartialProjectGQL:
        source = await ShowProject.find_one(ShowProject.id == self.project_id)
        if source is None:
            raise ValueError(f"Project not found on database for {self.project_id} collab server {self.server_id}")

        return PartialProjectGQL.from_db(source)

    @gql.field(description="The partial server information")
    async def server(self) -> PartialServerGQL:
        source = await ShowtimesServer.find_one(ShowtimesServer.server_id == self.server_id)
        if source is None:
            raise ValueError(f"Server not found on database for {self.server_id} collab server")

        return PartialServerGQL.from_db(source)

    @classmethod
    def from_db(
        cls: Type[ProjectCollabConfirmationInfoGQL],
        info: ShowtimesCollaborationInfo,
        fallback_project: Optional[str] = None,
    ) -> ProjectCollabConfirmationInfoGQL:
        project_id = str(info.project.ref.id) if info.project is not None else None
        if fallback_project is not None and project_id is None:
            project_id = fallback_project
        if project_id is None:
            raise ValueError(f"Project not found on database for {info.server.ref.id} collab project")
        return cls(
            server_id=str(info.server.ref.id),
            project_id=project_id,
        )


@gql.type(name="ProjectCollabConfirmation", description="A confirmation link to a project collab.")
class ProjectCollabConfirmationGQL:
    id: UUID = gql.field(description="The ID of this confirmation.")
    code: str = gql.field(description="The code of this confirmation link.")
    source: ProjectCollabConfirmationInfoGQL = gql.field(description="The source of this confirmation link.")
    target: ProjectCollabConfirmationInfoGQL = gql.field(description="The target of this confirmation link.")

    internal_id: gql.Private[str]  # ObjectId

    @classmethod
    def from_db(
        cls: Type[ProjectCollabConfirmationGQL], confirm: ShowtimesCollaboration
    ) -> ProjectCollabConfirmationGQL:
        return cls(
            id=confirm.collab_id,
            code=confirm.code,
            source=ProjectCollabConfirmationInfoGQL.from_db(confirm.source),
            target=ProjectCollabConfirmationInfoGQL.from_db(confirm.target),
            internal_id=str(confirm.id),
        )
