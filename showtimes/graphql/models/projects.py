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
from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn
from bson import ObjectId

from showtimes.controllers.prediction import PredictionInput, PredictionType, get_prediction_system
from showtimes.extensions.graphql.scalars import DateTime, Upload
from showtimes.models.database import (
    EpisodeStatus,
    ShowExternalAnilist,
    ShowExternalData,
    ShowExternalTMDB,
    ShowProject,
    ShowtimesCollaborationLinkSync,
)
from showtimes.tooling import get_logger

from .collab import ProjectCollabLinkGQL
from .common import ImageMetadataGQL, IntegrationGQL, IntegrationInputGQL, KeyValueInputGQL
from .enums import (
    ProjectExternalTypeGQL,
    ProjectInputAssigneeActionGQL,
    ProjectPredictionModelGQL,
    SearchExternalTypeGQL,
    SearchSourceTypeGQL,
)
from .partials import (
    PartialProjectInterface,
    ProjectAssigneeGQL,
    ProjectExternalAniListGQL,
    ProjectExternalTMDbGQL,
    ProjectStatusGQL,
    ShowPosterGQL,
)

__all__ = (
    "ProjectGQL",
    "ProjectInputExternalGQL",
    "ProjectInputAssigneeInfoGQL",
    "ProjectInputAssigneeGQL",
    "ProjectInputGQL",
    "ProjectPredictionGQL",
)
logger = get_logger("Showtimes.GraphQL.Showtimes.Projects")


@gql.type(name="ProjectPrediction", description="The project prediction information")
class ProjectPredictionGQL:
    server_id: gql.Private[str]
    count: gql.Private[int]
    type: gql.Private[str]
    priv_next_ep: gql.Private[int | None]

    @gql.field(description="Next episode prediction in days")
    async def next_episode(self, model: ProjectPredictionModelGQL = ProjectPredictionModelGQL.HISTORY) -> int | None:
        if self.priv_next_ep is None:
            # Every project is done
            return None

        system = get_prediction_system()
        try:
            result = await system.predict(
                PredictionInput(self.server_id, self.count, self.type, self.priv_next_ep),
                type=PredictionType.NEXT,
                use_simulated=model == ProjectPredictionModelGQL.SIMULATED,
            )
            return result
        except Exception as err:
            logger.error("Failed to predict overall", exc_info=err)
            return None

    @gql.field(description="Overall prediction in days")
    async def overall(self, model: ProjectPredictionModelGQL = ProjectPredictionModelGQL.HISTORY) -> int | None:
        if self.priv_next_ep is None:
            # Every project is done
            return None

        system = get_prediction_system()
        try:
            result = await system.predict(
                PredictionInput(self.server_id, self.count, self.type),
                type=PredictionType.OVERALL,
                use_simulated=model == ProjectPredictionModelGQL.SIMULATED,
            )
            return result
        except Exception as err:
            logger.error("Failed to predict overall", exc_info=err)
            return None

    @classmethod
    def from_db(cls: Type[ProjectPredictionGQL], project: ShowProject):
        _found_latest: EpisodeStatus | None = None
        for status in project.statuses:
            if status.is_released:
                continue
            _found_latest = status
            break
        count = len(project.statuses)
        mapped_types = {
            "SHOWS": "MOVIE" if count > 1 else "TV",
        }
        proj_type = mapped_types.get(project.type.value, project.type.value)
        return ProjectPredictionGQL(
            server_id=str(project.server_id),
            count=count,
            type=proj_type,
            priv_next_ep=_found_latest.episode if _found_latest is not None else None,
        )


@gql.type(name="Project", description="The project information")
class ProjectGQL(PartialProjectInterface):
    prediction: ProjectPredictionGQL = gql.field(description="The project prediction information")

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

    @gql.field(description="The project external information")
    async def external(self) -> ProjectExternalAniListGQL | ProjectExternalTMDbGQL:
        external_info = await ShowExternalData.find_one(
            ShowExternalData.id == ObjectId(self.ex_proj_id),
            with_children=True,
        )
        if external_info is None:
            raise ValueError(f"Project external information not found for {self.id}")

        if external_info.type == ProjectExternalTypeGQL.ANILIST:
            return ProjectExternalAniListGQL.from_db(cast(ShowExternalAnilist, external_info))
        elif external_info.type == ProjectExternalTypeGQL.TMDB:
            return ProjectExternalTMDbGQL.from_db(cast(ShowExternalTMDB, external_info))
        else:
            raise ValueError("Unknown project external type")

    @classmethod
    def from_db(cls: Type[ProjectGQL], project: ShowProject, *, only_latest: bool = False, include_last: bool = False):
        statuses: list[ProjectStatusGQL] = [ProjectStatusGQL.from_db(status) for status in project.statuses]
        if only_latest:
            _found_latest: ProjectStatusGQL | None = None
            for status in statuses:
                if status.is_released:
                    continue
                _found_latest = status
                break
            if _found_latest is None:
                statuses = []
                if include_last:
                    statuses.append(ProjectStatusGQL.from_db(project.statuses[-1]))
            else:
                statuses = [_found_latest]
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
            aliases=project.aliases,
            integrations=[IntegrationGQL.from_db(integration) for integration in project.integrations],
            assignments=[ProjectAssigneeGQL.from_db(actor) for actor in project.assignments],
            statuses=statuses,
            created_at=cast(DateTime, project.created_at),
            updated_at=cast(DateTime, project.updated_at),
            project_id=str(project.id),
            ex_proj_id=str(project.external.ref.id),
            type=project.type,
            prediction=ProjectPredictionGQL.from_db(project),
        )


@gql.input(name="ProjectInputExternal", description="The project external input information")
class ProjectInputExternalGQL:
    ref: str = gql.field(description="The reference ID of the project")
    type: SearchExternalTypeGQL = gql.field(description="The type of the project external data")
    source: SearchSourceTypeGQL = gql.field(description="The source of the project external data")


@gql.input(name="ProjectInputAssigneeInfo", description="The project assignee input information")
class ProjectInputAssigneeInfoGQL:
    id: str = gql.field(description="The ID of the assignee")
    name: str = gql.field(description="The name of the assignee")
    integrations: list[IntegrationInputGQL] | None = gql.field(
        default=gql.UNSET, description="List of integrations to add to the assignee"
    )


@gql.input(name="ProjectInputAssignee", description="The project assignee input information")
class ProjectInputAssigneeGQL:
    key: str = gql.field(description="The key of the assignee")
    info: ProjectInputAssigneeInfoGQL | None = gql.field(
        default=gql.UNSET, description="The information of the assignee"
    )
    mode: ProjectInputAssigneeActionGQL = gql.field(
        default=ProjectInputAssigneeActionGQL.UPSERT, description="The action to perform on the assignee"
    )


@gql.input(name="ProjectInputRoles", description="The project roles input information")
class ProjectInputRolesGQL:
    key: str = gql.field(description="The key of the role")
    name: str = gql.field(description="The name of the role")


@gql.input(name="ProjectInput", description="The project input information")
class ProjectInputGQL:
    name: str | None = gql.field(default=gql.UNSET, description="The name of the server")
    poster: Upload | None = gql.field(default=gql.UNSET, description="The avatar of the server")
    integrations: list[IntegrationInputGQL] | None = gql.field(
        default=gql.UNSET, description="List of integrations to add to the server"
    )
    external: ProjectInputExternalGQL | None = gql.field(
        default=gql.UNSET, description="The external project information"
    )
    assignees: list[ProjectInputAssigneeGQL] | None = gql.field(
        default=gql.UNSET,
        description=(
            "List of assignees to add to the project, if missing will use the default roles assignments per type"
        ),
    )
    aliases: list[str] | None = gql.field(default=gql.UNSET, description="List of aliases to add to the project")
    roles: list[ProjectInputRolesGQL] | None = gql.field(
        default=gql.UNSET, description="List of roles to add to the project, if missing will use the default roles"
    )
    count: int | None = gql.field(default=gql.UNSET, description="The episode/chapter count override for the project")


@gql.input(name="ProjectEpisodeInput", description="The project episode input information")
class ProjectEpisodeInput:
    episode: int = gql.field(description="The episode number")
    # roles will be a dynamic input, any data found in the database will be updated to the value provided.
    roles: list[KeyValueInputGQL[bool]] | None = gql.field(default=gql.UNSET, description="The roles for the episode")
    release: bool | None = gql.field(default=gql.UNSET, description="The release status of the episode")
    delay_reason: str | None = gql.field(default=gql.UNSET, description="The delay reason of the episode")
