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

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from beanie import Document, Link
from pydantic import BaseModel, Field

from showtimes.models.integrations import IntegrationId
from showtimes.utils import make_uuid

__all__ = (
    "ShowRSSFeedFormatterEmbed",
    "ShowRSSFeedFormatter",
    "ShowRSSFeed",
    "ShowRSS",
    "ShowRSSFeedEntryData",
)


class ShowRSSFeedFormatterEmbed(BaseModel):
    """
    A formatter that are based on Discord embeds.
    """

    title: str | None
    description: str | None
    url: str | None
    thumbnail: str | None
    image: str | None
    footer: str | None
    footer_image: str | None
    color: int = Field(default=0x525252)
    timestamped: bool = Field(default=False)


class ShowRSSFeedFormatter(BaseModel):
    """
    A formatter that are based on Discord embeds.
    """

    message: str | None = None
    embed: ShowRSSFeedFormatterEmbed | None = None

    @classmethod
    def default(cls: type[ShowRSSFeedFormatter]):
        return cls(
            message="📰 | Rilisan Baru: **{title}**\n{link}",
            embed=None,
        )


class ShowRSSFeed(Document):
    """
    The ShowRSS feed for a specific server.
    """

    url: str
    """The URL for this ShowRSS feed."""
    formatter: ShowRSSFeedFormatter = Field(default_factory=ShowRSSFeedFormatter.default)
    """The formatter for this ShowRSS feed."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """The integrations for this ShowRSS feed."""

    last_etag: str | None = Field(default=None)
    last_modified: str | None = Field(default=None)
    feed_id: UUID = Field(default_factory=make_uuid)
    created_at: float = Field(default_factory=lambda: datetime.utcnow().timestamp())

    class Settings:
        name = "ShowRSSFeed"


class ShowRSS(Document):
    """
    The ShowRSS feed.
    """

    feeds: list[Link[ShowRSSFeed]] = Field(default_factory=list)
    """The feeds for this ShowRSS."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """The integrations for this ShowRSS."""
    server_id: UUID = Field(default_factory=make_uuid)
    """The server ID for this ShowRSS."""

    class Settings:
        name = "ShowRSS"


@dataclass
class ShowRSSFeedEntryData:
    """Used internally"""

    entries: list[dict[str, Any]]
    feed: ShowRSSFeed
    etag: str | None
    modified: str | None
