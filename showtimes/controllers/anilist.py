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

from math import ceil
from typing import Optional, cast

import httpx
import pendulum
from pendulum.datetime import DateTime

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.models.anilist import AnilistFuzzyDate

from .._metadata import __version__
from ..utils import complex_walk
from .gqlapi import GraphQLClient, GraphQLResult, PredicateFunc
from .ratelimiter import NetworkRateLimiter

__all__ = (
    "AnilistAPI",
    "get_anilist_client",
    "init_anilist_client",
    "parse_anilist_fuzzy_date",
    "multiply_anilist_date",
    "rgbhex_to_rgbint",
)


class AnilistAPI:
    """
    A connection bucket to handle Anilist rate limiting.
    This class will make sure it's safe to request Anilist and avoid rate limiting...
    """

    BASE_API = "https://graphql.anilist.co"

    def __init__(self, session: httpx.AsyncClient, rate_limit: int = 90):
        self._sesi = session

        self._limiter = NetworkRateLimiter(rate_limit, 60)
        self._next_reset = -1
        self._rate_left = rate_limit

        self._requester = GraphQLClient(self.BASE_API, session)

    async def close(self):
        await self._sesi.aclose()

    def _handle_x_rate_headers(self, headers: httpx.Headers):
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if reset is not None:
            self._limiter.next_reset = reset
        if limit is not None:
            self._limiter.limit = limit
        if remaining is not None:
            self._limiter.remaining = remaining

    async def handle(
        self, query: str, variables: dict | None = None, operation_name: Optional[str] = None
    ) -> GraphQLResult:  # type: ignore
        if variables is None:
            variables = {}
        async for _ in self._limiter:
            requested = await self._requester.query(query, variables, operation_name)
            self._handle_x_rate_headers(requested.headers)
            return requested

    async def paginate(
        self,
        query: str,
        variables: Optional[dict] = None,
        operation_name: Optional[str] = None,
        predicate: PredicateFunc | None = None,
    ):
        variables = variables or {}

        def internal_function(data: Optional[dict]):
            if data is None:
                return False, None, "page"
            page_info = cast(Optional[dict], complex_walk(data, "Page.pageInfo"))
            if page_info is None:
                return False, None, "page"
            has_next_page = cast(bool, page_info.get("hasNextPage", False))
            current_page = cast(int, page_info.get("currentPage", 0))
            per_page = cast(int, page_info.get("perPage", 0))
            total_data = cast(int, page_info.get("total", 0))
            total_pages = ceil(total_data / per_page)
            if current_page == total_pages:
                has_next_page = False
            return has_next_page, current_page + 1, "page"

        await self._limiter.drip()
        async for result, pageInfo in self._requester.paginate(
            query, predicate or internal_function, variables, operation_name
        ):
            self._handle_x_rate_headers(result.headers)
            yield result
            if pageInfo.hasMore:
                await self._limiter.drip()
            else:
                break


_ANILIST_CLIENT: Optional[AnilistAPI] = None


def get_anilist_client():
    global _ANILIST_CLIENT
    if _ANILIST_CLIENT is None:
        raise ShowtimesControllerUninitializedError(name="Anilist Client")
    return _ANILIST_CLIENT


async def init_anilist_client(session: httpx.AsyncClient | None = None):
    global _ANILIST_CLIENT

    if _ANILIST_CLIENT is None:
        session = session or httpx.AsyncClient(
            headers={"User-Agent": f"Showtimes/v{__version__} (+https://github.com/naoTimesdev/showtimes)"}
        )
        _ANILIST_CLIENT = AnilistAPI(session)


# Helpers


def parse_anilist_fuzzy_date(fuzzy_date: AnilistFuzzyDate) -> DateTime | None:
    year: int | None = fuzzy_date.get("year", None)
    month: int | None = fuzzy_date.get("month", None)
    day: int | None = fuzzy_date.get("day", None)

    ext_dt: list[str] = []
    data_dt: list[str] = []
    if year is not None:
        ext_dt.append("YYYY")
        data_dt.append(str(year))
    if month is not None:
        ext_dt.append("M")
        data_dt.append(str(month))
    if day is not None:
        ext_dt.append("D")
        data_dt.append(str(day))

    if len(data_dt) < 2:
        return None

    return pendulum.from_format("-".join(data_dt), "-".join(ext_dt))


def multiply_anilist_date(start_time: int, episode: int) -> DateTime:
    WEEKS = 7 * 24 * 60 * 60
    expected = start_time + (episode * WEEKS)
    return pendulum.from_timestamp(expected)


def rgbhex_to_rgbint(color: str | None) -> int:
    if color is None:
        return 2012582

    hexed_str = color.lstrip("#").upper()
    R = int(hexed_str[0:2], 16)
    G = int(hexed_str[2:4], 16)
    B = int(hexed_str[4:6], 16)
    return 256 * 256 * R + 256 * G + B
