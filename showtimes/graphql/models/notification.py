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
from uuid import UUID

import strawberry as gql

from showtimes.extensions.graphql.scalars import UNIXTimestamp
from showtimes.graphql.models.collab import ProjectCollabConfirmationGQL
from showtimes.models.notification import (
    Notification,
    NotificationData,
    NotificationDataAdminBroadcast,
    NotificationDataCollab,
)

__all__ = (
    "NotificationDataAdminBroadcastGQL",
    "NotificationGQL",
)

@gql.type(
    name="NotificationDataAdminBroadcastGQL", description="The data for the notification for the admin broadcast."
)
class NotificationDataAdminBroadcastGQL:
    message: str = gql.field(description="The message for the broadcast.")
    """The message for the broadcast."""
    link: str | None = gql.field(description="The external link for the broadcast.")
    """The external link for the broadcast."""


@gql.type(name="Notification", description="Notification payload.")
class NotificationGQL:
    id: str = gql.field(description="The ID of the notification.")
    """The ID of the notification."""
    target: UUID = gql.field(description="The target for the notification.")
    """The target for the notification."""
    created: UNIXTimestamp = gql.field(description="The unix timestamp of when the notification was created.")
    """The unix timestamp of when the notification was created."""
    read: bool = gql.field(description="Whether the notification has been read or not.")
    """Whether the notification has been read or not."""

    internal_data: gql.Private[NotificationData]

    @gql.field(description="The data for the notification.")
    async def data(self) -> NotificationDataAdminBroadcastGQL | ProjectCollabConfirmationGQL | None:
        if isinstance(self.internal_data, NotificationDataAdminBroadcast):
            return NotificationDataAdminBroadcastGQL(message=self.internal_data.message, link=self.internal_data.link)
        elif isinstance(self.internal_data, NotificationDataCollab):
            return ProjectCollabConfirmationGQL.from_notification(self.internal_data)

    @classmethod
    def from_notification(cls: Type[NotificationGQL], data: Notification) -> NotificationGQL:
        return cls(
            id=str(data.id),
            target=UUID(data.target),
            created=int(data.created),
            read=data.read,
            internal_data=data.data,
        )
