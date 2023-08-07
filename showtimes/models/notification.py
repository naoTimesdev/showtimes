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

from enum import Enum
from typing import TypeAlias
from uuid import UUID

import pendulum
from msgspec import Struct, field

__all__ = (
    "NotificationType",
    "NotificationDataCollabSource",
    "NotificationDataCollab",
    "NotificationDataAdminBroadcast",
    "NotificationData",
    "Notification",
)


class NotificationType(str, Enum):
    PENDING_COLLAB = "PENDING_COLLAB"
    """Indicates that a collaboration request is pending for the user."""
    ADMIN_BROADCAST = "ADMIN_BROADCAST"


class NotificationDataCollabSource(Struct):
    server: str  # ObjectId, stringified
    """The server that the collaboration request is for."""
    project: str | None  # ObjectId, stringified
    """The project that the collaboration request is for."""


class NotificationDataCollab(Struct):
    id: UUID
    """The ID of the collaboration request."""
    code: str
    """The code of the collaboration request."""
    source: NotificationDataCollabSource
    """The source of the collaboration request."""
    target: NotificationDataCollabSource
    """The target of the collaboration request."""
    internal_id: str  # ObjectId, stringified


class NotificationDataAdminBroadcast(Struct):
    message: str
    """The message of the broadcast."""
    link: str | None = None
    """The link of the broadcast."""


NotificationData: TypeAlias = NotificationDataCollab | NotificationDataAdminBroadcast


class Notification(Struct):
    id: UUID
    """The ID of the notification."""
    target: str  # Identifier
    """Who is the notification for?"""
    type: NotificationType
    """The type of the notification."""
    data: NotificationData
    """The data of the notification."""
    created: float = field(default_factory=lambda: pendulum.now("UTC").float_timestamp)
    """The timestamp of when the notification was created."""
    read: bool = False
    """Has the notification been read?"""
