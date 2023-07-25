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

from uuid import UUID

import strawberry as gql

from showtimes.controllers.pubsub import get_pubsub
from showtimes.graphql.models.partials import PartialProjectGQL, PartialServerGQL, ProjectStatusGQL
from showtimes.models.database import ShowProject, ShowtimesServer
from showtimes.models.timeseries import PubSubType, TimeSeriesProjectEpisodeChanges
from showtimes.tooling import get_logger

__all__ = ("subs_showtimes_project_episode_updated",)
logger = get_logger("Showtimes.GraphQL.Subscriptions.Showtimes")


@gql.type
class ProjectEpisodeUpdateSubs:
    old: list[ProjectStatusGQL] = gql.field(description="The old project statuses")
    """The old project statuses"""
    new: list[ProjectStatusGQL] = gql.field(description="The new project statuses")
    """The new project statuses"""

    project_id: UUID = gql.field(description="The project ID")
    server_id: UUID = gql.field(description="The server ID")

    @gql.field(description="The server that this project belongs to")
    async def server(self) -> PartialServerGQL:
        server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == self.server_id)
        if server_info is None:
            raise ValueError("Server not found")

        return PartialServerGQL.from_db(server_info)

    @gql.field(description="The project that this episode belongs to")
    async def project(self) -> PartialProjectGQL:
        project_info = await ShowProject.find_one(ShowProject.show_id == self.project_id)
        if project_info is None:
            raise ValueError("Project not found")

        return PartialProjectGQL.from_db(project_info)

    @classmethod
    def from_db(cls: type[ProjectEpisodeUpdateSubs], ts_data: TimeSeriesProjectEpisodeChanges):
        return cls(
            old=[ProjectStatusGQL.from_db(status) for status in ts_data.old],
            new=[ProjectStatusGQL.from_db(status) for status in ts_data.new],
            project_id=ts_data.model_id,
            server_id=ts_data.server_id,
        )


async def subs_showtimes_project_episode_updated(
    server_id: UUID | None = None,
    project_id: UUID | None = None,
):
    if server_id is None and project_id is None:
        raise ValueError("Must provide either server ID or project ID")

    pubsub = get_pubsub()
    if server_id is not None:
        pub_topic = PubSubType.EPISODE_CHANGE.make(server_id)
        logger.info(f"Subscribing to episode updates for server {server_id} w/ topic {pub_topic}")
        async for payload in pubsub.subscribe(pub_topic):
            if isinstance(payload, TimeSeriesProjectEpisodeChanges):
                yield ProjectEpisodeUpdateSubs.from_db(payload)
    elif project_id is not None:
        pub_topic = PubSubType.EPISODE_CHANGE.make(project_id)
        logger.info(f"Subscribing to episode updates for project {project_id} w/ topic {pub_topic}")
        async for payload in pubsub.subscribe(PubSubType.EPISODE_CHANGE.make(project_id)):
            if isinstance(payload, TimeSeriesProjectEpisodeChanges):
                yield ProjectEpisodeUpdateSubs.from_db(payload)
