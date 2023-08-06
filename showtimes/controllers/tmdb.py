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

from typing import Type, TypeVar

import httpx
import msgspec

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.models.tmdb import TMDBErrorResponse, TMDBMultiResponse

from .._metadata import __version__

__all__ = (
    "TMDbAPI",
    "get_tmdb_client",
    "init_tmdb_client",
)
RespT = TypeVar("RespT", bound=msgspec.Struct)


class TMDbAPI:
    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, *, session: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._session = session

    async def close(self) -> None:
        if self._session:
            await self._session.aclose()

    def _make_query(self, base_query: dict | None = None):
        base_query = base_query or {}
        base_query.update({"api_key": self._api_key})

        return base_query

    async def request(self, method: str, url: str, *, type: Type[RespT], **kwargs) -> RespT | TMDBErrorResponse:
        if self._session is None:
            self._session = httpx.AsyncClient(
                headers={"User-Agent": f"Showtimes/v{__version__} (+https://github.com/naoTimesdev/showtimes)"}
            )

        resp = await self._session.request(method, url, **kwargs)

        text_data = await resp.aread()
        try:
            return msgspec.json.decode(text_data, type=TMDBErrorResponse)
        except msgspec.DecodeError:
            return msgspec.json.decode(text_data, type=type)

    async def search(self, query: str, page: int = 1) -> TMDBMultiResponse | TMDBErrorResponse:
        """
        Search for a title in TMDb.

        Parameters
        ----------
        query: :class:`str`
            The title to search for.

        """

        params = self._make_query(
            {
                "query": query,
                "include_adult": "true",
                "page": str(page),
            }
        )

        response = await self.request("GET", f"{self.BASE_URL}/search/multi", type=TMDBMultiResponse, params=params)
        return response

    async def get_series(self, series_id: int):
        """
        Get a series from TMDb.

        Parameters
        ----------
        series_id: :class:`int`
            The ID of the series to get.

        """

        response = await self.request("GET", f"{self.BASE_URL}/tv/{series_id}", type=TMDBMultiResponse)
        return response

    async def get_movie(self, series_id: int):
        """
        Get a series from TMDb.

        Parameters
        ----------
        series_id: :class:`int`
            The ID of the series to get.

        """

        response = await self.request("GET", f"{self.BASE_URL}/movie/{series_id}", type=TMDBMultiResponse)
        return response


_TMDB_CLIENT: TMDbAPI | None = None


def get_tmdb_client() -> TMDbAPI:
    global _TMDB_CLIENT
    if _TMDB_CLIENT is None:
        raise ShowtimesControllerUninitializedError("TMDb Client")
    return _TMDB_CLIENT


async def init_tmdb_client(api_key: str):
    global _TMDB_CLIENT
    if _TMDB_CLIENT is None:
        _TMDB_CLIENT = TMDbAPI(api_key)
