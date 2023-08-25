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

from showtimes.controllers.pubsub import get_pubsub
from showtimes.graphql.models.showrss import ShowRSSEntryGQL
from showtimes.models.pubsub import PubSubType
from showtimes.models.timeseries import TimeSeriesShowRSSFeedEntry
from showtimes.tooling import get_logger

__all__ = ("subs_showrss_feeds",)
logger = get_logger("Showtimes.GraphQL.Subscriptions.ShowRSS")


async def subs_showrss_feeds(
    server_id: UUID | None = None,
    feeds_id: UUID | None = None,
    start_from: int | None = None,
):
    pubsub = get_pubsub()
    if isinstance(server_id, UUID):
        if isinstance(start_from, int):
            # Fetch the latest episode changes
            logger.info(f"Fetching latest rss entry for server {server_id} | {start_from}")
            async for prepayload in TimeSeriesShowRSSFeedEntry.find(
                TimeSeriesShowRSSFeedEntry.server_id == server_id,
                TimeSeriesShowRSSFeedEntry.ts >= datetime.utcfromtimestamp(start_from),
            ):
                yield await ShowRSSEntryGQL.from_timeseries(prepayload)

        pub_topic = PubSubType.RSS_SERVER.make(server_id)
        logger.info(f"Subscribing to server RSS feeds: {pub_topic}")
        async for payload in pubsub.subscribe(pub_topic):
            if isinstance(payload, TimeSeriesShowRSSFeedEntry):
                yield await ShowRSSEntryGQL.from_timeseries(payload)
    elif isinstance(feeds_id, UUID):
        if isinstance(start_from, int):
            # Fetch the latest episode changes
            logger.info(f"Fetching latest rss entry for feeds {server_id} | {start_from}")
            async for prepayload in TimeSeriesShowRSSFeedEntry.find(
                TimeSeriesShowRSSFeedEntry.oobj_id == feeds_id,
                TimeSeriesShowRSSFeedEntry.ts >= datetime.utcfromtimestamp(start_from),
            ):
                yield await ShowRSSEntryGQL.from_timeseries(prepayload)

        pub_topic = PubSubType.RSS_FEED.make(feeds_id)
        logger.info(f"Subscribing to RSS feeds: {pub_topic}")
        async for payload in pubsub.subscribe(pub_topic):
            if isinstance(payload, TimeSeriesShowRSSFeedEntry):
                yield await ShowRSSEntryGQL.from_timeseries(payload)
    else:
        if isinstance(start_from, int):
            # Fetch the latest episode changes
            logger.info(f"Fetching latest rss entry for feeds {server_id} | {start_from}")
            async for prepayload in TimeSeriesShowRSSFeedEntry.find(
                TimeSeriesShowRSSFeedEntry.ts >= datetime.utcfromtimestamp(start_from),
            ):
                yield await ShowRSSEntryGQL.from_timeseries(prepayload)

        pub_topic = PubSubType.RSS_MULTI.make("ALL")
        logger.info(f"Subscribing to all RSS feeds: {pub_topic}")
        async for payload in pubsub.subscribe(pub_topic):
            if isinstance(payload, TimeSeriesShowRSSFeedEntry):
                yield await ShowRSSEntryGQL.from_timeseries(payload)
