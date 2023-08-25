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
from uuid import UUID

from beanie import Document, Insert, Replace, Save, SaveChanges, Update, ValidateOnSave, after_event
from pendulum.datetime import DateTime
from pydantic import Field

from ._doc import _coerce_to_pendulum

__all__ = (
    "ShowtimesPremium",
    "ShowtimesPremiumKind",
)
AllEvent = [Insert, Replace, Update, Save, SaveChanges, ValidateOnSave]


class ShowtimesPremiumKind(str, Enum):
    SHOWTIMES = "showtimes"
    """Kind for ShowtimesServer"""
    SHOWRSS = "showrss"
    """Kind for ShowRSS"""


class ShowtimesPremium(Document):
    """
    The premium ticket features of Showtimes.
    """

    target: UUID
    """The target object this premium ticket is for."""
    kind: ShowtimesPremiumKind
    """The kind of premium ticket this is."""
    expires_at: DateTime = Field(default_factory=DateTime.utcnow)
    """The date and time this premium ticket expires at."""
    created_at: DateTime = Field(default_factory=DateTime.utcnow)
    """The date and time this premium ticket was created at."""

    @after_event(*AllEvent)
    def coerce_pendulum(self):
        _coerce_to_pendulum(self)

    def _save_state(self) -> None:
        _coerce_to_pendulum(self)
        super()._save_state()

    class Config:
        arbitrary_types_allowed = True
