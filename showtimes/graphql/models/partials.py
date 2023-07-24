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

from typing import Optional, Type, cast
from uuid import UUID

import strawberry as gql
from bson import ObjectId

from showtimes.extensions.graphql.scalars import UNIXTimestamp
from showtimes.graphql.models.enums import ProjectExternalTypeGQL
from showtimes.models.database import (
    EpisodeStatus,
    RoleActor,
    ShowActor,
    ShowExternalAnilist,
    ShowExternalData,
    ShowExternalEpisode,
    ShowExternalTMDB,
    ShowProject,
    ShowtimesServer,
)

from .common import ImageMetadataGQL, IntegrationGQL

__all__ = (
    "PartialServerGQL",
    "ShowPosterGQL",
    "ProjectExternalEpisodeGQL",
    "ProjectExternalGQL",
    "ProjectExternalAniListGQL",
    "ProjectExternalTMDbGQL",
    "ProjectAssigneeInfoGQL",
    "ProjectAssigneeGQL",
    "ProjectStatusRoleGQL",
    "ProjectStatusGQL",
    "PartialProjectGQL",
)


@gql.interface(name="PartialServer", description="The partial server information")
class PartialServerGQL:
    id: UUID = gql.field(description="The server ID")
    """The server ID"""
    name: str = gql.field(description="The server name")
    """The server username"""
    avatar: Optional[ImageMetadataGQL] = gql.field(description="The server image")
    """The server image"""

    server_id: gql.Private[str]  # ObjectId
    project_links: gql.Private[list[str]]  # ObjectId
    owner_links: gql.Private[list[str]]  # ObjectId

    @classmethod
    def from_db(cls: Type[PartialServerGQL], server: ShowtimesServer):
        return cls(
            id=server.server_id,
            name=server.name,
            avatar=ImageMetadataGQL.from_db(server.avatar) if server.avatar else None,
            server_id=str(server.id),
            project_links=[str(i.ref.id) for i in server.projects],
            owner_links=[str(i.ref.id) for i in server.owners],
        )


@gql.type(name="ShowPoster", description="The show poster information")
class ShowPosterGQL:
    image: ImageMetadataGQL = gql.field(description="The show poster image")
    color: int | None = gql.field(description="The show poster color")


@gql.type(name="ProjectExternalEpisode", description="The project external episode information")
class ProjectExternalEpisodeGQL:
    episode: int = gql.field(description="The episode number")
    season: int = gql.field(description="The season number")
    title: str | None = gql.field(description="The episode title")
    airtime: UNIXTimestamp | None = gql.field(description="The episode airtime, in UNIX timestamp")

    @classmethod
    def from_db(cls: Type[ProjectExternalEpisodeGQL], episode: ShowExternalEpisode):
        return cls(
            episode=episode.episode,
            season=episode.season,
            title=episode.title,
            airtime=int(episode.airtime) if episode.airtime is not None else None,
        )


@gql.interface(name="ProjectExternal", description="The project external information")
class ProjectExternalGQL:
    episodes: list[ProjectExternalEpisodeGQL] = gql.field(description="The project external episodes")
    type: ProjectExternalTypeGQL = gql.field(description="The project external type")
    start_time: UNIXTimestamp | None = gql.field(
        description="The project external AniList start time, in UNIX timestamp"
    )


@gql.type(name="ProjectExternalAniList", description="The project external AniList information")
class ProjectExternalAniListGQL(ProjectExternalGQL):
    id: str = gql.field(description="The project external AniList ID")
    mal_id: str | None = gql.field(description="The project external AniList MyAnimeList ID")

    internal_id: gql.Private[str]  # ObjectId

    @classmethod
    def from_db(cls: Type[ProjectExternalAniListGQL], external: ShowExternalAnilist):
        return cls(
            id=str(external.ani_id),
            mal_id=external.mal_id,
            episodes=[ProjectExternalEpisodeGQL.from_db(episode) for episode in external.episodes],
            type=ProjectExternalTypeGQL.ANILIST,
            start_time=int(external.start_time) if external.start_time is not None else None,
            internal_id=str(external.id),
        )


@gql.type(name="ProjectExternalTMDb", description="The project external TMDb information")
class ProjectExternalTMDbGQL(ProjectExternalGQL):
    id: str = gql.field(description="The project external TMDb ID")

    internal_id: gql.Private[str]  # ObjectId

    @classmethod
    def from_db(cls: Type[ProjectExternalTMDbGQL], external: ShowExternalTMDB):
        return cls(
            id=str(external.tmdb_id),
            episodes=[ProjectExternalEpisodeGQL.from_db(episode) for episode in external.episodes],
            type=ProjectExternalTypeGQL.ANILIST,
            start_time=int(external.start_time) if external.start_time is not None else None,
            internal_id=str(external.id),
        )


@gql.type(name="ProjectAssigneeInfo", description="The project assignee actor information")
class ProjectAssigneeInfoGQL:
    id: UUID = gql.field(description="The actor ID")
    name: str = gql.field(description="The actor name")
    integrations: list[IntegrationGQL] = gql.field(description="The actor integrations")

    internal_id: gql.Private[str]  # ObjectId

    @classmethod
    def from_db(cls: Type[ProjectAssigneeInfoGQL], actor: RoleActor):
        return cls(
            id=actor.actor_id,
            name=actor.name,
            integrations=[IntegrationGQL.from_db(integration) for integration in actor.integrations],
            internal_id=str(actor.id),
        )


@gql.type(name="ProjectAssignee", description="The project assignee information of each role")
class ProjectAssigneeGQL:
    key: str = gql.field(description="The role key")

    assignee_id: gql.Private[str | None]  # ObjectId

    @classmethod
    def from_db(cls: Type[ProjectAssigneeGQL], actor: ShowActor):
        return cls(
            key=actor.key,
            assignee_id=str(actor.actor.ref.id) if actor.actor is not None else None,
        )

    @gql.field(description="The project assignee actor information")
    async def assignee(self) -> ProjectAssigneeInfoGQL | None:
        actor = await RoleActor.find_one(RoleActor.id == ObjectId(self.assignee_id))
        if actor is None:
            return None
        return ProjectAssigneeInfoGQL.from_db(actor)


@gql.type(name="ProjectStatusRole", description="The project status information of each episodes of each role")
class ProjectStatusRoleGQL:
    key: str = gql.field(description="The role key")
    name: str = gql.field(description="The role long name")
    done: bool = gql.field(description="Whether the role has finished its job or not")


@gql.type(name="ProjectStatus", description="The project status information of each episodes")
class ProjectStatusGQL:
    episode: int = gql.field(description="The episode number")
    is_released: bool = gql.field(description="Whether the episode is released")
    airing_at: UNIXTimestamp | None = gql.field(description="The episode airtime, in UNIX timestamp")
    roles: list[ProjectStatusRoleGQL] = gql.field(description="The project status information of each role")
    delay_reason: str | None = gql.field(description="The episode delay reason")

    @classmethod
    def from_db(cls: Type[ProjectStatusGQL], episode: EpisodeStatus):
        return cls(
            episode=episode.episode,
            is_released=episode.is_released,
            airing_at=int(episode.airing_at) if episode.airing_at is not None else None,
            roles=[
                ProjectStatusRoleGQL(
                    key=role.key,
                    name=role.name,
                    done=role.finished,
                )
                for role in episode.statuses
            ],
            delay_reason=episode.delay_reason,
        )


@gql.interface(name="PartialProject", description="The partial project information")
class PartialProjectGQL:
    id: UUID = gql.field(description="The project ID")
    """The project ID"""
    title: str = gql.field(description="The project title")
    """The project title"""
    poster: Optional[ShowPosterGQL] = gql.field(description="The project poster")
    """The project poster"""
    server_id: UUID = gql.field(description="The server ID")
    """The associated server ID"""
    integrations: list[IntegrationGQL] = gql.field(description="The project integrations")
    """The project integrations"""
    assignments: list[ProjectAssigneeGQL] = gql.field(description="The project assignments")
    """The project assignments"""
    statuses: list[ProjectStatusGQL] = gql.field(description="The project statuses of each episode")
    """The project statuses of each episode"""

    project_id: gql.Private[str]  # ObjectId
    ex_proj_id: gql.Private[str]  # ObjectId

    @gql.field(description="The project external information")
    async def external(self) -> ProjectExternalGQL:
        external_info = await ShowExternalData.find_one(ShowExternalData.id == ObjectId(self.ex_proj_id))
        if external_info is None:
            raise ValueError("Project external information not found")

        if external_info.type == ProjectExternalTypeGQL.ANILIST:
            return ProjectExternalAniListGQL.from_db(cast(ShowExternalAnilist, external_info))
        elif external_info.type == ProjectExternalTypeGQL.TMDB:
            return ProjectExternalTMDbGQL.from_db(cast(ShowExternalTMDB, external_info))
        else:
            raise ValueError("Unknown project external type")

    @classmethod
    def from_db(cls: Type[PartialProjectGQL], project: ShowProject, *, only_latest: bool = False):
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
            integrations=[IntegrationGQL.from_db(integration) for integration in project.integrations],
            assignments=[ProjectAssigneeGQL.from_db(actor) for actor in project.assignments],
            statuses=statuses,
            project_id=str(project.id),
            ex_proj_id=str(project.external.ref.id),
        )
