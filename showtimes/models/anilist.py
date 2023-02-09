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

from typing import Generic, Literal, Optional, TypeVar

from .abstract import AttributeDict

AT = TypeVar("AT")

__all__ = (
    "AnilistFuzzyDate",
    "AnilistAiringScheduleNode",
    "AnilistAiringSchedules",
    "AnilistCoverImage",
    "AnilistTitle",
    "AnilistAnimeScheduleResult",
    "AnilistAnimeInfoResult",
    "AnilistQueryMedia",
)
AnilistAnimeFormat = Literal[
    "TV",
    "TV_SHORT",
    "MOVIE",
    "SPECIAL",
    "OVA",
    "ONA",
    "MUSIC",
]
AnilistBooksFormat = Literal["MANGA", "NOVEL", "ONE_SHOT"]
AnilistFormat = AnilistAnimeFormat | AnilistBooksFormat


class AnilistFuzzyDate(AttributeDict):
    year: Optional[str]
    month: Optional[str]
    day: Optional[str]


class AnilistAiringScheduleNode(AttributeDict):
    id: int
    episode: int
    airingAt: int


class AnilistAiringSchedules(AttributeDict):
    nodes: list[AnilistAiringScheduleNode]


class AnilistCoverImage(AttributeDict):
    medium: str
    large: str
    extraLarge: Optional[str]
    # Hexadecimal color code.
    color: str


class AnilistTitle(AttributeDict):
    romaji: str
    english: str
    native: str


class AnilistAnimeScheduleResult(AttributeDict):
    id: int
    format: AnilistFormat
    episodes: Optional[int]
    startDate: AnilistFuzzyDate
    airingSchedule: AnilistAiringSchedules


class AnilistAnimeInfoResult(AnilistAnimeScheduleResult):
    idMal: Optional[int]
    title: AnilistTitle
    coverImage: AnilistCoverImage


class AnilistQueryMedia(AttributeDict, Generic[AT]):
    Media: AT
