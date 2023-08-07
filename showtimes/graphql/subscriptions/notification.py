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

from showtimes.controllers.pubsub import get_pubsub
from showtimes.controllers.redisdb import get_redis
from showtimes.graphql.models.notification import NotificationGQL
from showtimes.models.notification import Notification
from showtimes.models.pubsub import PubSubType

__all__ = ("subs_notification",)


async def subs_notification(user_id: str, server_id: str | None = None):
    pubsub = get_pubsub()
    redis = get_redis()
    pubsub_target = [user_id]
    all_notifications = await redis.getall(f"showtimesv2:notification:{user_id}", type=Notification)
    if server_id is not None:
        pubsub_target.append(server_id)
        all_notifications.extend(await redis.getall(f"showtimesv2:notification:{server_id}", type=Notification))

    all_notifications.sort(key=lambda x: x.created)
    for notification in all_notifications:
        if not notification.read:
            yield NotificationGQL.from_notification(notification)

    async for payload in pubsub.subscribe(PubSubType.NOTIIFCATION):
        if isinstance(payload, Notification):
            if payload.target not in pubsub_target:
                continue
            yield NotificationGQL.from_notification(payload)
