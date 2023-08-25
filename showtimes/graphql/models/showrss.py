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

import asyncio
from typing import Any
from uuid import UUID

import markdown
import pendulum
import strawberry as gql
from beanie.operators import In as OpIn
from bson import ObjectId

from showtimes.extensions.graphql.scalars import DateTime
from showtimes.extensions.markdown.plaintext import PlainTextExtension
from showtimes.formatter import OptionalFormatter
from showtimes.graphql.models.common import IntegrationGQL
from showtimes.models.showrss import ShowRSS, ShowRSSFeed, ShowRSSFeedFormatter, ShowRSSFeedFormatterEmbed
from showtimes.models.timeseries import TimeSeriesShowRSSFeedEntry

__all__ = (
    "ShowRSSFormatterEmbedGQL",
    "ShowRSSFormatterGQL",
    "ShowRSSFeedGQL",
    "ShowRSSGQL",
    "ShowRSSEntryFormatValueGQL",
    "ShowRSSEntryEmbedFormattedGQL",
    "ShowRSSEntryFormattedGQL",
    "ShowRSSEntryGQL",
)
PLAIN_MD = markdown.Markdown(extensions=[PlainTextExtension()])


@gql.type(
    name="ShowRSSFeedFormatterEmbed",
    description="A formatter embed information for a RSS feed, based on Discord embed.",
)
class ShowRSSFormatterEmbedGQL:
    title: str | None = gql.field(description="The title for the embed.")
    """The title for the embed."""
    description: str | None = gql.field(description="The description for the embed.")
    """The description for the embed."""
    url: str | None = gql.field(description="The URL for the embed.")
    """The URL for the embed."""
    thumbnail: str | None = gql.field(description="The thumbnail for the embed.")
    """The thumbnail for the embed."""
    image: str | None = gql.field(description="The image for the embed.")
    """The image for the embed."""
    footer: str | None = gql.field(description="The footer for the embed.")
    """The footer for the embed."""
    footer_image: str | None = gql.field(description="The footer image for the embed.")
    """The footer image for the embed."""
    color: int = gql.field(description="The color for the embed. (Int color)")
    """The color for the embed."""
    timestamped: bool = gql.field(description="Whether the embed should be timestamped or not.")
    """Whether the embed should be timestamped or not."""

    @classmethod
    def from_db(cls: type[ShowRSSFormatterEmbedGQL], data: ShowRSSFeedFormatterEmbed) -> ShowRSSFormatterEmbedGQL:
        return cls(
            title=data.title,
            description=data.description,
            url=data.url,
            thumbnail=data.thumbnail,
            image=data.image,
            footer=data.footer,
            footer_image=data.footer_image,
            color=data.color,
            timestamped=data.timestamped,
        )


@gql.type(name="ShowRSSFormatter", description="A formatter information for a RSS feed.")
class ShowRSSFormatterGQL:
    message: str | None = gql.field(description="The message for the formatter.")
    """The message for the formatter."""
    embed: ShowRSSFormatterEmbedGQL | None = gql.field(description="The embed for the formatter.")

    @classmethod
    def from_db(cls: type[ShowRSSFormatterGQL], data: ShowRSSFeedFormatter) -> ShowRSSFormatterGQL:
        return cls(
            message=data.message,
            embed=ShowRSSFormatterEmbedGQL.from_db(data.embed) if data.embed is not None else None,
        )


@gql.type(name="ShowRSSFeed", description="A RSS feed for a server.")
class ShowRSSFeedGQL:
    id: UUID = gql.field(description="The ID of the RSS feed.")
    """The ID of the RSS feed."""
    url: str = gql.field(description="The URL for the RSS feed.")
    """The URL for the RSS feed."""
    integrations: list[IntegrationGQL] = gql.field(description="The integrations for the RSS feed.")
    """The integrations for the RSS feed."""
    formatter: ShowRSSFormatterGQL = gql.field(description="The formatter for the RSS feed.")
    """The formatter for the RSS feed."""

    @classmethod
    def from_db(cls: type[ShowRSSFeedGQL], data: ShowRSSFeed) -> ShowRSSFeedGQL:
        return cls(
            id=data.feed_id,
            url=data.url,
            integrations=[IntegrationGQL.from_db(x) for x in data.integrations],
            formatter=ShowRSSFormatterGQL.from_db(data.formatter),
        )


@gql.type(name="ShowRSS", description="A RSS information for a server.")
class ShowRSSGQL:
    id: UUID = gql.field(description="The ID of the server.")
    """The ID of the server."""
    integrations: list[IntegrationGQL] = gql.field(description="The integrations for the server.")
    """The integrations for the server."""

    feed_ids: gql.Private[list[ObjectId]]

    @gql.field(description="The RSS feeds for the server.")
    async def feeds(self) -> list[ShowRSSFeedGQL]:
        feeds = await ShowRSSFeed.find(OpIn(ShowRSSFeed.id, self.feed_ids)).to_list()
        return [ShowRSSFeedGQL.from_db(x) for x in feeds]

    @classmethod
    def from_db(cls: type[ShowRSSGQL], data: ShowRSS) -> ShowRSSGQL:
        return cls(
            id=data.server_id,
            integrations=[IntegrationGQL.from_db(x) for x in data.integrations],
            feed_ids=[x.ref.id for x in data.feeds],
        )


@gql.type(name="ShowRSSEntryFormatValue", description="A formatted RSS entry value.")
class ShowRSSEntryFormatValueGQL:
    markdown: str | None = gql.field(description="The markdown format for the value.")
    """The markdown format for the value."""
    raw: str | None = gql.field(description="The raw unformatted value.")
    """The raw unformatted value."""

    @gql.field(description="The text format for this value, no formatting.")
    async def text(self) -> str | None:
        if self.markdown is None:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, PLAIN_MD.convert, self.markdown)

    @gql.field(description="The HTML format for the value.")
    async def html(self) -> str | None:
        if self.markdown is None:
            return None
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, markdown.markdown, self.markdown)


def _create_format_value(content: str | None, data: dict[str, Any]) -> ShowRSSEntryFormatValueGQL:
    if content is None:
        return ShowRSSEntryFormatValueGQL(markdown=None, raw=None)
    return ShowRSSEntryFormatValueGQL(
        markdown=OptionalFormatter.format(content, **data),
        raw=content,
    )


@gql.type(name="ShowRSSEntryEmbedFormatted", description="A formatted embed RSS entry.")
class ShowRSSEntryEmbedFormattedGQL:
    data: gql.Private[dict[str, Any]]
    formatter: gql.Private[ShowRSSFormatterEmbedGQL]

    @gql.field(description="The title for the embed.")
    async def title(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.title, self.data)

    @gql.field(description="The description for the embed.")
    async def description(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.description, self.data)

    @gql.field(description="The URL for the embed.")
    async def url(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.url, self.data)

    @gql.field(description="The thumbnail for the embed.")
    async def thumbnail(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.thumbnail, self.data)

    @gql.field(description="The image for the embed.")
    async def image(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.image, self.data)

    @gql.field(description="The footer for the embed.")
    async def footer(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.footer, self.data)

    @gql.field(description="The footer image for the embed.")
    async def footer_image(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.footer_image, self.data)

    @classmethod
    def from_db(cls: type[ShowRSSEntryEmbedFormattedGQL], data: dict[str, Any], formatted: ShowRSSFormatterEmbedGQL):
        return cls(
            data=data,
            formatter=formatted,
        )


@gql.type(name="ShowRSSEntryFormatted", description="A formatted RSS entry.")
class ShowRSSEntryFormattedGQL:
    embed: ShowRSSEntryEmbedFormattedGQL | None = gql.field(description="The embed for this entry.")
    """The embed for this entry."""

    data: gql.Private[dict[str, Any]]
    formatter: gql.Private[ShowRSSFormatterGQL]

    @gql.field(description="The message for this entry.")
    async def message(self) -> ShowRSSEntryFormatValueGQL:
        return _create_format_value(self.formatter.message, self.data)

    @classmethod
    def from_db(
        cls: type[ShowRSSEntryFormattedGQL], data: dict[str, Any], feed: ShowRSSFeedGQL
    ) -> ShowRSSEntryFormattedGQL:
        return cls(
            data=data,
            formatter=feed.formatter,
            embed=ShowRSSEntryEmbedFormattedGQL.from_db(data, feed.formatter.embed) if feed.formatter.embed else None,
        )


@gql.type(name="ShowRSSEntry", description="A RSS entry.")
class ShowRSSEntryGQL:
    timestamp: DateTime = gql.field(description="The timestamp of the update")
    feed: ShowRSSFeedGQL = gql.field(description="The RSS feed for the entry.")
    server_id: gql.Private[UUID]
    data: gql.Private[dict[str, Any]]

    @gql.field(description="The server for the entry.")
    async def server(self) -> ShowRSSGQL:
        server = await ShowRSS.find_one(ShowRSS.server_id == self.server_id)
        if server is None:
            raise ValueError("Server not found.")

        return ShowRSSGQL.from_db(server)

    @gql.field(description="The formatted entry.")
    async def formatted(self) -> ShowRSSEntryFormattedGQL:
        return ShowRSSEntryFormattedGQL.from_db(self.data, self.feed)

    @classmethod
    async def from_timeseries(cls: type[ShowRSSEntryGQL], entry: TimeSeriesShowRSSFeedEntry):
        feed = await ShowRSSFeed.find_one(ShowRSSFeed.feed_id == entry.model_id)
        if feed is None:
            raise ValueError("Feed not found.")

        return cls(
            timestamp=pendulum.instance(entry.ts),
            feed=ShowRSSFeedGQL.from_db(feed),
            server_id=entry.server_id,
            data=entry.data,
        )
