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

from beanie import Document, Granularity, Insert, Save, SaveChanges, TimeSeriesConfig, after_event
from pydantic import Field

from showtimes.controllers.pubsub import get_pubsub
from showtimes.models.database import EpisodeStatus
from showtimes.models.pubsub import PubSubType

__all__ = (
    "TimeSeriesProjectEpisodeChanges",
    "TimeSeriesServerDelete",
    "TimeSeriesProjectDelete",
)


class TimeSeriesBase(Document):
    ts: datetime = Field(default_factory=datetime.utcnow)
    """The timestamp of the change"""
    model_id: UUID
    """The model ID, can be the project, server, or anything"""

    class Settings:
        timeseries = TimeSeriesConfig(
            time_field="ts",
            meta_field="project_id",
            granularity=Granularity.seconds,
            expire_after_seconds=None,
        )
        name = "ShowtimesTimeSeries"
        is_root = True


class TimeSeriesProjectEpisodeChanges(TimeSeriesBase):
    server_id: UUID
    """The server ID"""
    old: list[EpisodeStatus]
    """The old episode status"""
    new: list[EpisodeStatus]
    """The new episode status"""

    @after_event(Insert, Save, SaveChanges)
    def publish_changes(self):
        pubsub = get_pubsub()
        # Two publish
        pubsub.publish(PubSubType.EPISODE_CHANGE.make(self.model_id), self)
        pubsub.publish(PubSubType.EPISODE_CHANGE.make(self.server_id), self)


class TimeSeriesServerDelete(TimeSeriesBase):
    @after_event(Insert, Save, SaveChanges)
    def publish_changes(self):
        pubsub = get_pubsub()
        # Two publish
        pubsub.publish(PubSubType.SERVER_DELETE.make(self.model_id), self)
        pubsub.publish(PubSubType.SERVER_DELETE.make("ALL"), self)


class TimeSeriesProjectDelete(TimeSeriesBase):
    server_id: UUID
    """The server ID"""

    @after_event(Insert, Save, SaveChanges)
    def publish_changes(self):
        pubsub = get_pubsub()
        # Two publish
        pubsub.publish(PubSubType.PROJECT_DELETE.make(self.model_id), self)
        pubsub.publish(PubSubType.PROJECT_DELETE.make(id=self.server_id), self)
        pubsub.publish(PubSubType.PROJECT_DELETE.make("ALL"), self)
