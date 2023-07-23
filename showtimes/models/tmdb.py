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
from typing import Optional

from msgspec import Struct

__all__ = (
    "TMDbMediaType",
    "TMDbMultiResult",
    "TMDBMultiResponse",
    "TMDBErrorResponse",
)


class TMDbMediaType(str, Enum):
    MOVIE = "movie"
    TV = "tv"
    COLLECTION = "collection"
    COMPANY = "company"
    KEYWORD = "keyword"
    PERSON = "person"


class TMDbMultiResult(Struct):
    id: int
    """:class:`int`: The ID of the result"""
    adult: bool
    """:class:`bool`: Whether the result is adult or not"""
    media_type: TMDbMediaType
    """:class:`TMDbMediaType`: The media type of the result"""
    original_language: str
    """:class:`str`: The original language of the result"""

    poster_path: Optional[str] = None
    """:class:`Optional[str]`: The poster path of the result"""
    backdrop_path: Optional[str] = None
    """:class:`Optional[str]`: The backdrop path of the result"""
    release_date: Optional[str] = None
    """:class:`Optional[str]`: The release date of the result"""
    first_air_date: Optional[str] = None
    """:class:`Optional[str]`: The first air date of the result"""
    title: Optional[str] = None
    """:class:`Optional[str]`: The title of the result"""
    name: Optional[str] = None
    """:class:`Optional[str]`: The title of the result"""
    original_title: Optional[str] = None
    """:class:`Optional[str]`: The original title of the result"""
    original_name: Optional[str] = None
    """:class:`Optional[str]`: The original title of the result"""

    @property
    def year(self) -> int | None:
        """The year of the result"""
        if self.release_date:
            return int(self.release_date.split("-")[0])
        elif self.first_air_date:
            return int(self.first_air_date.split("-")[0])
        return None

    @property
    def poster_url(self) -> str | None:
        if self.poster_path:
            return f"https://image.tmdb.org/t/p/w780{self.poster_path}"


class TMDBMultiResponse(Struct):
    """Response from TMDb's multi search API"""

    total_results: int
    """:class:`int`: The total results of the search"""
    total_pages: int
    """:class:`int`: The total pages of the search"""
    page: int
    """:class:`int`: The current page of the search"""
    results: list[TMDbMultiResult]
    """:class:`list[TMDbMultiResult]`: The results of the search"""


class TMDBErrorResponse(Struct):
    """Response from TMDb's error API"""

    success: bool
    """:class:`bool`: Whether the request was successful or not"""
    status_code: int
    """:class:`int`: The status code of the request"""
    status_message: str
    """:class:`str`: The status message of the request"""
