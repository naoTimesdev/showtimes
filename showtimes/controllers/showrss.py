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
import re
from datetime import datetime
from typing import cast
from urllib.parse import urlparse
from uuid import UUID

import feedparser
import httpx
import pendulum
from beanie.operators import In as OpIn
from ftfy import TextFixerConfig, fix_text
from markdownify import markdownify
from pendulum.datetime import DateTime

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.models.premium import ShowtimesPremium, ShowtimesPremiumKind
from showtimes.models.showrss import ShowRSS, ShowRSSFeed, ShowRSSFeedEntryData
from showtimes.models.timeseries import TimeSeriesShowRSSFeedEntry
from showtimes.tooling import get_logger

from .._metadata import __version__ as app_version

__all__ = (
    "ShowRSSHandler",
    "initialize_showrss",
    "get_showrss",
)
logger = get_logger("Showtimes.Controllers.ShowRSS")
ImageExtract = re.compile(r"!\[[^\]]*\]\((?P<filename>.*?)(?=\"|\))(?P<optionalpart>\".*\")?\)", re.I)


def _parse_modified(modified: str) -> str | None:
    parsed = pendulum.parser.parse(modified)
    if not isinstance(parsed, DateTime):
        return None
    # RFC 1123-compliant
    return parsed.to_rfc1123_string()


async def async_rss_feed_fetch(
    url: str, etag: str | None = None, modified: str | None = None
) -> tuple[feedparser.FeedParserDict | None, str | None, str | None]:
    aio_timeout = httpx.Timeout(30.0)
    headers = {
        "Accept": "application/rss+xml, application/rdf+xml;q=0.8, application/atom+xml;q=0.6, application/xml;q=0.4, text/xml;q=0.4",  # noqa: E501
        "User-Agent": f"Showtimes-RSS/{app_version} (+https://github.com/naoTimesdev/showtimes)",
    }
    if etag is not None:
        headers["If-None-Match"] = etag
    if modified is not None:
        parse_modified = _parse_modified(modified)
        if parse_modified is not None:
            headers["If-Modified-Since"] = modified
    async with httpx.AsyncClient(timeout=aio_timeout, headers=headers) as client:
        resp = await client.get(url)
        resp_data = await resp.aread()
    loop = asyncio.get_running_loop()
    feedparsed = await loop.run_in_executor(None, feedparser.parse, resp_data)
    last_modified = resp.headers.get("Last-Modified", None)
    last_etag = resp.headers.get("ETag", None)
    return feedparsed, last_modified, last_etag


def cleanup_encoding_error(text: str) -> str:
    config = TextFixerConfig(
        fix_character_width=False,
        uncurl_quotes=False,
        explain=False,
    )

    return fix_text(text, config=config)


def first_match_in_list(targets: list[dict], key: str):
    for data in targets:
        try:
            valid = data[key]
            return valid
        except KeyError:
            pass
    return None


def normalize_rss_data(entries: dict, base_url: str = "") -> dict:
    """Remove unnecessary tags that basically useless for the bot."""
    KEYS_TO_REMOVE = [
        "title_detail",
        "links",
        "authors",
        "author_detail",
        "content",
        "updated",
        "guidislink",
        "summary_detail",
        "comments",
        "href",
        "wfw_commentrss",
        "slash_comments",
    ]

    if base_url.endswith("/"):
        base_url = base_url[:-1]

    for KEY in KEYS_TO_REMOVE:
        try:
            del entries[KEY]
        except KeyError:
            pass

    tagar = entries.get("tags", [])
    proper_tag = []
    for tag in tagar:
        proper_tag.append(tag["term"])
    entries["tags"] = proper_tag

    if "media_thumbnail" in entries:
        try:
            matching_image = first_match_in_list(entries["media_thumbnail"], "url")
            if matching_image is None:
                entries["media_thumbnail"] = ""
            else:
                entries["media_thumbnail"] = matching_image
        except IndexError:
            entries["media_thumbnail"] = ""
        except KeyError:
            entries["media_thumbnail"] = ""
    else:
        entries["media_thumbnail"] = ""

    if "summary" in entries:
        parsed_summary = cleanup_encoding_error(markdownify(entries["summary"]))
        extracted_images = list(ImageExtract.finditer(parsed_summary))
        first_image_link = None
        for extracted in extracted_images:
            if extracted:
                filename_match = extracted.group("filename")
                all_match = extracted.group()
                parsed_summary = parsed_summary.replace(all_match, "")
                parse_url = urlparse(filename_match)
                if parse_url.netloc == "":
                    real_url = parse_url.path
                    if real_url.startswith("/"):
                        real_url = real_url[1:]
                    query_params = parse_url.query
                    first_image_link = f"{base_url}/{real_url}"
                    if query_params != "":
                        first_image_link += f"?{query_params}"
                else:
                    skema_url = parse_url.scheme
                    if skema_url == "":
                        skema_url = "http"
                    first_image_link = f"{skema_url}://{parse_url.netloc}{parse_url.path}"
                    if parse_url.query != "":
                        first_image_link += f"?{parse_url.query}"
        entries["summary"] = cleanup_encoding_error(parsed_summary)
        if first_image_link is not None and not entries["media_thumbnail"]:
            entries["media_thumbnail"] = first_image_link

    if "description" in entries:
        parsed_description = cleanup_encoding_error(markdownify(entries["description"]))
        entries["description"] = parsed_description

    if "media_content" in entries:
        media_url = entries["media_content"]
        if media_url:
            matching_image = first_match_in_list(media_url, "url")
            if matching_image is not None:
                entries["media_content"] = matching_image
        else:
            del entries["media_content"]

    return entries


async def async_showrss_fetch_feed(models: ShowRSSFeed) -> ShowRSSFeedEntryData | None:
    loop = asyncio.get_running_loop()
    try:
        feed, last_modified, last_etag = await asyncio.wait_for(
            async_rss_feed_fetch(models.url, etag=models.last_etag, modified=models.last_modified),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        return None

    if last_modified is not None:
        # Parse into ISO 8601
        last_modified = pendulum.from_format(last_modified, "ddd, DD MMM YYYY HH:mm:ss ZZ").isoformat()

    if feed is None:
        return None

    try:
        base_url = cast(str | None, cast(feedparser.FeedParserDict, feed.get("feed")).get("link"))
        if base_url is None:
            base_url = models.url
        parsed_base_url = urlparse(base_url)
    except (KeyError, IndexError):
        parsed_base_url = urlparse(models.url)

    scheme_url = parsed_base_url.scheme
    if scheme_url == "":
        scheme_url = "http"
    actual_base_url = f"{scheme_url}://{parsed_base_url.netloc}"

    entries = feed.get("entries", [])

    filtered_entries: list[dict] = []
    for entry in entries:
        normalized_entry = await loop.run_in_executor(None, normalize_rss_data, entry, actual_base_url)
        filtered_entries.append(normalized_entry)

    return ShowRSSFeedEntryData(filtered_entries, models, last_etag, last_modified)


class ShowRSSHandler:
    def __init__(
        self,
        interval: float = 300.0,
        interval_premium: float = 180.0,
        limit: int = 3,
        limit_premium: int = 5,
    ) -> None:
        self._interval = interval
        self._interval_premium = interval_premium
        self._limit = limit
        self._limit_preimum = limit_premium

        self._task_handlers: dict[str, asyncio.Task] = {}
        self._feeds: dict[str, list[ShowRSSFeed]] = {}

    def _deregister_rss_schedule(self, task: asyncio.Task):
        try:
            logger.info(f"RSS task {task.get_name()} has finished running")
            del self._task_handlers[task.get_name()]
        except (ValueError, KeyError, IndexError, AttributeError):
            logger.error(f"Failed to deregister task {task.get_name()}, probably missing!")

    async def _check_and_create_entry_data(self, server_id: str, feed: ShowRSSFeed):
        try:
            fetch_data = await async_showrss_fetch_feed(feed)
        except Exception as exc:
            logger.exception(f"Error while fetching feed {feed.feed_id} | {feed.url}", exc_info=exc)
            return
        if fetch_data is None:
            logger.debug(f"Feed {feed.feed_id} is missing/failed | {feed.url}")
            return

        if not fetch_data.entries:
            logger.debug(f"Feed {feed.feed_id} entries is empty | {feed.url}")

        existing_entries = await TimeSeriesShowRSSFeedEntry.find(
            TimeSeriesShowRSSFeedEntry.model_id == feed.feed_id,
            TimeSeriesShowRSSFeedEntry.server_id == UUID(server_id),
        ).to_list()

        link_data = [entry.data["link"] for entry in existing_entries]
        link_data = [link for link in link_data if link is not None]

        new_entries = []
        for entry in fetch_data.entries:
            if entry["link"] not in link_data:
                new_entries.append(entry)

        logger.debug(f"Got {len(new_entries)} new entries for feed {feed.feed_id} | {feed.url}")
        if not new_entries:
            return

        for entry in new_entries:
            new_entry = TimeSeriesShowRSSFeedEntry(
                server_id=UUID(server_id),
                model_id=feed.feed_id,
                data=entry,
            )
            await new_entry.save()  # type: ignore

    async def _get_all_rss(self, is_premium: bool = False):
        if not self._feeds:
            return
        premium_data = await ShowtimesPremium.find(
            ShowtimesPremium.kind == ShowtimesPremiumKind.SHOWRSS,
            ShowtimesPremium.expires_at > DateTime.utcnow(),
        ).to_list()

        all_premium_server = [str(premium.target) for premium in premium_data]

        feeds_to_fetch: list[tuple[str, list[ShowRSSFeed]]] = []
        for key, feed_data in self._feeds.items():
            if key in all_premium_server and is_premium:
                feeds_to_fetch.append((key, feed_data))
            elif key not in all_premium_server and not is_premium:
                feeds_to_fetch.append((key, feed_data))

        fetch_type = "premium" if is_premium else "regular"
        right_now = datetime.utcnow().timestamp()
        for srv_id, feeds in feeds_to_fetch:
            for feed in feeds:
                logger.debug(f"Fetching RSS feeds for feed {feed} | {srv_id}")
                task_name = f"showrss-feed-fetcher-{fetch_type}-{srv_id}-{feed.feed_id!s}-{right_now}"
                feed_task = asyncio.create_task(self._check_and_create_entry_data(srv_id, feed), name=task_name)
                feed_task.add_done_callback(self._deregister_rss_schedule)
                self._task_handlers[task_name] = feed_task

    async def _regular_executor(self):
        logger.info(f"Starting regular RSS feeds fetcher, with interval of {self._interval} seconds...")
        while True:
            try:
                logger.debug("Fetching RSS feeds (Regular)")
                await self._get_all_rss(is_premium=False)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error while fetching RSS feeds", exc_info=exc)
            await asyncio.sleep(self._interval)

    async def _premium_executor(self):
        logger.info(f"Starting regular RSS feeds fetcher, with interval of {self._interval} seconds...")
        while True:
            try:
                logger.debug("Fetching RSS feeds (Premium)")
                await self._get_all_rss(is_premium=True)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Error while fetching RSS feeds", exc_info=exc)
            await asyncio.sleep(self._interval_premium)

    async def start(self):
        # Starting the tasks
        logger.info("Initializing RSS feeds...")
        all_servers = await ShowRSS.find().to_list()

        logger.info(f"Got {len(all_servers)} sources to fetch")
        for server in all_servers:
            feed_ids = [feed.ref.id for feed in server.feeds]
            logger.info(f"  Fetching premium info for {server.server_id}...")
            premium_ticket = await ShowtimesPremium.find_one(
                ShowtimesPremium.kind == ShowtimesPremiumKind.SHOWRSS,
                ShowtimesPremium.target == server.server_id,
            )
            limit = self._limit if premium_ticket is None else self._limit_preimum
            logger.info(f"  Fetching {limit} feeds data for {server.server_id}...")
            fetched_feeds = (
                await ShowRSSFeed.find(OpIn(ShowRSSFeed.id, feed_ids)).sort("+created_at").limit(limit).to_list()
            )
            self._feeds[str(server.server_id)] = fetched_feeds

        logger.info("Starting RSS feeds fetcher...")
        right_now = datetime.utcnow().timestamp()
        regular_task = asyncio.create_task(self._regular_executor(), name=f"showrss-main-task-regular-{right_now}")
        regular_task.add_done_callback(self._deregister_rss_schedule)
        premium_task = asyncio.create_task(self._premium_executor(), name=f"showrss-main-task-premium-{right_now}")
        premium_task.add_done_callback(self._deregister_rss_schedule)
        self._task_handlers[f"showrss-main-task-regular-{right_now}"] = regular_task
        self._task_handlers[f"showrss-main-task-premium-{right_now}"] = premium_task

    async def close(self):
        # Fire the cancellation
        logger.info("Cancelling RSS feeds fetcher...")
        for task in self._task_handlers.values():
            task.cancel()
        logger.info("Waiting for RSS feeds fetcher to finish...")
        await asyncio.gather(*self._task_handlers.values(), return_exceptions=True)
        logger.info("RSS feeds fetcher finished")

    async def add_feed(self, server_id: str, feed: ShowRSSFeed):
        if server_id not in self._feeds:
            self._feeds[server_id] = []
        self._feeds[server_id].append(feed)
        logger.info(f"Added feed {feed.feed_id} to server {server_id}")

    async def remove_feed(self, server_id: str, feed: ShowRSSFeed):
        if server_id not in self._feeds:
            return
        self._feeds[server_id].remove(feed)
        logger.info(f"Removed feed {feed.feed_id} from server {server_id}")


_SHOWRSS_HANDLER: ShowRSSHandler | None = None


async def initialize_showrss(
    interval: float = 300.0,
    interval_premium: float = 180.0,
    limit: int = 3,
    limit_premium: int = 5,
):
    global _SHOWRSS_HANDLER

    if _SHOWRSS_HANDLER is not None:
        return _SHOWRSS_HANDLER

    _SHOWRSS_HANDLER = ShowRSSHandler(
        interval=interval,
        interval_premium=interval_premium,
        limit=limit,
        limit_premium=limit_premium,
    )
    await _SHOWRSS_HANDLER.start()

    return _SHOWRSS_HANDLER


def get_showrss() -> ShowRSSHandler:
    global _SHOWRSS_HANDLER

    if _SHOWRSS_HANDLER is None:
        raise ShowtimesControllerUninitializedError("ShowRSS")

    return _SHOWRSS_HANDLER
