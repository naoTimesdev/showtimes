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

from math import ceil
from typing import TYPE_CHECKING, Optional, cast

import aiohttp

from .gqlapi import GraphQLClient, GraphQLResult
from .ratelimiter import NetworkRateLimiter
from ..utils import complex_walk

if TYPE_CHECKING:
    from multidict import CIMultiDictProxy


class AnilistAPI:
    """
    A connection bucket to handle Anilist rate limiting.
    This class will make sure it's safe to request Anilist and avoid rate limiting...
    """

    BASE_API = "https://graphql.anilist.co"

    def __init__(self, session: aiohttp.ClientSession, rate_limit: int = 90):
        self._sesi = session

        self._limiter = NetworkRateLimiter(rate_limit, 60)
        self._next_reset = -1
        self._rate_left = rate_limit

        self._requester = GraphQLClient(self.BASE_API, session)

    def _handle_x_rate_headers(self, headers: "CIMultiDictProxy[str]"):
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if reset is not None:
            self._limiter.next_reset = reset
        if limit is not None:
            self._limiter.limit = limit
        if remaining is not None:
            self._limiter.remaining = remaining

    async def handle(self, query: str, variables: dict = {}) -> GraphQLResult:  # type: ignore
        async for _ in self._limiter:
            requested = await self._requester.query(query, variables)
            self._handle_x_rate_headers(requested.headers)
            return requested

    async def paginate(self, query: str, variables: Optional[dict] = None):
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
        async for result, pageInfo in self._requester.paginate(query, internal_function, variables):
            self._handle_x_rate_headers(result.headers)
            yield result
            if pageInfo.hasMore:
                await self._limiter.drip()
            else:
                break
