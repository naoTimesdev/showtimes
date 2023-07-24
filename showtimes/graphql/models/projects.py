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

import strawberry as gql
from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn

from showtimes.graphql.models.collab import ProjectCollabLinkGQL
from showtimes.models.database import ShowProject, ShowtimesCollaborationLinkSync

from .common import ImageMetadataGQL, IntegrationGQL
from .partials import PartialProjectGQL, ProjectAssigneeGQL, ProjectStatusGQL, ShowPosterGQL

__all__ = ("ProjectGQL",)


@gql.type(name="Project", description="The project information")
class ProjectGQL(PartialProjectGQL):
    @gql.field(description="The project collaboration sync status")
    async def collaborations(self) -> ProjectCollabLinkGQL | None:
        collab_sync = await ShowtimesCollaborationLinkSync.find_one(
            OpAnd(
                OpIn(ShowtimesCollaborationLinkSync.projects, [self.id]),
                OpIn(ShowtimesCollaborationLinkSync.servers, [self.server_id]),
            ),
        )
        if collab_sync is None:
            return None

        return ProjectCollabLinkGQL.from_db(self.server_id, self.id, collab_sync)

    @classmethod
    def from_db(cls: Type[ProjectGQL], project: ShowProject):
        return cls(
            id=project.show_id,
            title=project.title,
            poster=ShowPosterGQL(
                image=ImageMetadataGQL.from_db(project.poster.image),
                color=project.poster.color,
            )
            if project.poster is not None
            else None,
            server_id=project.server_id,
            integrations=[IntegrationGQL.from_db(integration) for integration in project.integrations],
            assignments=[ProjectAssigneeGQL.from_db(actor) for actor in project.assignments],
            statuses=[ProjectStatusGQL.from_db(status) for status in project.statuses],
            project_id=str(project.id),
            ex_proj_id=str(project.external.ref.id),
        )
