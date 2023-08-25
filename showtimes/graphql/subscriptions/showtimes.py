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

from datetime import datetime
from uuid import UUID

import pendulum
import strawberry as gql

from showtimes.controllers.pubsub import get_pubsub
from showtimes.extensions.graphql.scalars import DateTime
from showtimes.graphql.models.partials import PartialProjectGQL, PartialServerGQL, ProjectStatusGQL
from showtimes.models.database import ShowProject, ShowtimesServer
from showtimes.models.pubsub import PubSubType
from showtimes.models.timeseries import (
    TimeSeriesProjectDelete,
    TimeSeriesProjectEpisodeChanges,
    TimeSeriesServerDelete,
)
from showtimes.tooling import get_logger

__all__ = (
    "subs_showtimes_project_episode_updated",
    "subs_showtimes_server_delete",
    "subs_showtimes_project_delete",
)
logger = get_logger("Showtimes.GraphQL.Subscriptions.Showtimes")


@gql.type
class ProjectEpisodeUpdateSubs:
    timestamp: DateTime = gql.field(description="The timestamp of the update")
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
            timestamp=pendulum.instance(ts_data.ts),
            old=[ProjectStatusGQL.from_db(status) for status in ts_data.old],
            new=[ProjectStatusGQL.from_db(status) for status in ts_data.new],
            project_id=ts_data.model_id,
            server_id=ts_data.server_id,
        )


@gql.type(description="The response for simple ID-based deletion")
class SubsResponse:
    id: UUID = gql.field(description="The ID of the model being deleted")
    extra_id: UUID | None = gql.field(description="The extra ID of the model being deleted")
    timestamp: DateTime = gql.field(description="The timestamp of the deletion")


async def subs_showtimes_project_episode_updated(
    server_id: UUID | None = None,
    project_id: UUID | None = None,
    start_from: int | None = None,
):
    if server_id is None and project_id is None:
        raise ValueError("Must provide either server ID or project ID")

    pubsub = get_pubsub()
    if server_id is not None:
        if isinstance(start_from, int):
            # Fetch the latest episode changes
            logger.info(f"Fetching latest episode changes for server {server_id} | {start_from}")
            async for prepayload in TimeSeriesProjectEpisodeChanges.find(
                TimeSeriesProjectEpisodeChanges.server_id == server_id,
                TimeSeriesProjectEpisodeChanges.ts >= datetime.utcfromtimestamp(start_from),
            ):
                yield ProjectEpisodeUpdateSubs.from_db(prepayload)

        pub_topic = PubSubType.EPISODE_CHANGE.make(server_id)
        logger.info(f"Subscribing to episode updates for server {server_id} w/ topic {pub_topic}")
        async for payload in pubsub.subscribe(pub_topic):
            if isinstance(payload, TimeSeriesProjectEpisodeChanges):
                yield ProjectEpisodeUpdateSubs.from_db(payload)
    elif project_id is not None:
        if isinstance(start_from, int):
            # Fetch the latest episode changes
            logger.info(f"Fetching latest episode changes for project {project_id} | {start_from}")
            async for prepayload in TimeSeriesProjectEpisodeChanges.find(
                TimeSeriesProjectEpisodeChanges.model_id == project_id,
                TimeSeriesProjectEpisodeChanges.ts >= datetime.utcfromtimestamp(start_from),
            ):
                yield ProjectEpisodeUpdateSubs.from_db(prepayload)

        pub_topic = PubSubType.EPISODE_CHANGE.make(project_id)
        logger.info(f"Subscribing to episode updates for project {project_id} w/ topic {pub_topic}")
        async for payload in pubsub.subscribe(PubSubType.EPISODE_CHANGE.make(project_id)):
            if isinstance(payload, TimeSeriesProjectEpisodeChanges):
                yield ProjectEpisodeUpdateSubs.from_db(payload)


async def subs_showtimes_server_delete(server_id: UUID | None = None):
    pubsub = get_pubsub()
    pub_topic = PubSubType.SERVER_DELETE.make("ALL")
    if server_id is not None:
        pub_topic = PubSubType.SERVER_DELETE.make(server_id)
    logger.info(f"Subscribing to server deletion for server {server_id} w/ topic {pub_topic}")
    async for payload in pubsub.subscribe(pub_topic):
        if isinstance(payload, TimeSeriesServerDelete):
            yield SubsResponse(id=payload.model_id, extra_id=None, timestamp=pendulum.instance(payload.ts))


async def subs_showtimes_project_delete(model_id: UUID | None = None):
    pubsub = get_pubsub()
    pub_topic = PubSubType.PROJECT_DELETE.make("ALL")
    if model_id is not None:
        pub_topic = PubSubType.PROJECT_DELETE.make(model_id)
    logger.info(f"Subscribing to server deletion for server {model_id} w/ topic {pub_topic}")
    async for payload in pubsub.subscribe(pub_topic):
        if isinstance(payload, TimeSeriesProjectDelete):
            yield SubsResponse(id=payload.model_id, extra_id=payload.server_id, timestamp=pendulum.instance(payload.ts))
