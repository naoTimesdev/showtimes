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

from typing import Union, cast

import strawberry as gql
from strawberry.types import Info

from showtimes.controllers.anilist import get_anilist_client
from showtimes.controllers.tmdb import get_tmdb_client
from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.extensions.graphql.context import SessionQLContext
from showtimes.graphql.models.enums import SearchExternalTypeGQL, SearchSourceTypeGQL, SearchTitleTypeGQL
from showtimes.graphql.models.fallback import ErrorCode, Result
from showtimes.graphql.models.search import SearchResult, SearchResults, SearchResultTitle
from showtimes.models.anilist import AnilistAnimeInfoResult, AnilistPagedMedia, AnilistQueryMedia
from showtimes.models.tmdb import TMDBErrorResponse

__all__ = ("QuerySearch",)


class AnilistSearch(AnilistAnimeInfoResult):
    season: str | None
    seasonYear: int | None  # noqa: N815
    chapters: int | None
    volumes: int | None


ANILIST_QUERY = """
query shows($search:String) {
    Page (page:1,perPage:15) {
        media(search:$search,type:ANIME) {
            id
            idMal
            format
            season
            seasonYear
            episodes
            chapters
            volumes
            startDate {
                year
            }
            title {
                romaji
                native
                english
            }
            coverImage {
                medium
                large
                extraLarge
            }
        }
    }
}

query books($search:String) {
    Page (page:1,perPage:15) {
        media(search:$search,type:MANGA) {
            id
            idMal
            format
            season
            seasonYear
            episodes
            chapters
            volumes
            startDate {
                year
            }
            title {
                romaji
                native
                english
            }
            coverImage {
                medium
                large
                extraLarge
            }
        }
    }
}
"""


def _coerce_anilist_format(format_str: str) -> SearchExternalTypeGQL:
    format_str = format_str.upper()
    shows = ["TV", "TV_SHORT", "SPECIAL", "OVA", "ONA", "MUSIC"]
    books = ["MANGA", "NOVEL", "ONE_SHOT"]
    if format_str in shows:
        return SearchExternalTypeGQL.SHOWS
    if format_str == "MOVIE":
        return SearchExternalTypeGQL.MOVIE
    if format_str in books:
        return SearchExternalTypeGQL.BOOKS
    return SearchExternalTypeGQL.UNKNOWN


def _coerce_tmdb_format(format_str: str) -> SearchExternalTypeGQL:
    format_str = format_str.upper()
    if format_str == "TV":
        return SearchExternalTypeGQL.SHOWS
    if format_str == "MOVIE":
        return SearchExternalTypeGQL.MOVIE
    return SearchExternalTypeGQL.UNKNOWN


async def do_anilist_search(
    query, type: SearchExternalTypeGQL, title_sort: SearchTitleTypeGQL = SearchTitleTypeGQL.ENGLISH
) -> Result | SearchResults:
    if type == SearchExternalTypeGQL.UNKNOWN:
        return Result(success=False, message="Unknown search type", code="COMMON_SEARCH_UNKNOWN_TYPE")
    act_type = type.value
    if type == SearchExternalTypeGQL.MOVIE:
        act_type = "shows"
    anilist_client = get_anilist_client()

    responses = await anilist_client.handle(ANILIST_QUERY, {"search": query}, operation_name=act_type)
    if responses is None:
        return Result(success=False, message="Anilist API is down", code=ErrorCode.AnilistAPIUnavailable)

    if responses.data is None:
        return Result(success=False, message="Invalid results!", code=ErrorCode.AnilistAPIError)

    response_data = cast(AnilistPagedMedia[AnilistQueryMedia[list[AnilistSearch]]], responses.data)
    if response_data.Page is None:
        return Result(success=False, message="Invalid results!", code=ErrorCode.AnilistAPIError)

    medias = response_data.Page.media
    if medias is None:
        return Result(success=False, message="Invalid results!", code=ErrorCode.AnilistAPIError)

    if not medias:
        return SearchResults(count=0, results=[])

    parsed_results: list[SearchResult] = []
    for media in medias:
        sel_title: str | None = None
        if title_sort == SearchTitleTypeGQL.ENGLISH:
            sel_title = media.title.english
        elif title_sort == SearchTitleTypeGQL.ROMANIZED:
            sel_title = media.title.romaji
        elif title_sort == SearchTitleTypeGQL.NATIVE:
            sel_title = media.title.native
        if sel_title is None:
            sel_title = (
                media.title.english or media.title.romaji or media.title.native or f"Unknown {type.value.capitalize()}"
            )
        result = SearchResult(
            id=str(media.id),
            title=sel_title,
            titles=SearchResultTitle(
                english=media.title.english,
                romanized=media.title.romaji,
                native=media.title.native,
            ),
            format=_coerce_anilist_format(media.format),
            season=media.season,
            year=media.seasonYear or media.startDate.year or -1,
            cover_url=media.coverImage.extraLarge or media.coverImage.large or media.coverImage.medium,
            count=media.episodes or media.chapters or media.volumes,
            source=SearchSourceTypeGQL.ANILIST,
        )
        parsed_results.append(result)
    return SearchResults(count=len(parsed_results), results=parsed_results)


async def do_tmdb_search(
    query: str, title_sort: SearchTitleTypeGQL = SearchTitleTypeGQL.ENGLISH
) -> SearchResults | Result:
    tmdb_client = get_tmdb_client()

    response = await tmdb_client.search(query)
    if isinstance(response, TMDBErrorResponse):
        return Result(success=False, message=response.status_message, code=ErrorCode.TMDbAPIError)

    parsed_results: list[SearchResult] = []
    for result in response.results:
        if result.media_type.lower() not in ["tv", "movie"]:
            continue
        sel_title: str | None = None
        eng_title = result.name or result.title
        original_title = result.original_name or result.original_title
        if title_sort == SearchTitleTypeGQL.ENGLISH:
            sel_title = result.name or result.title
        else:
            sel_title = result.original_name or result.original_title
        if sel_title is None:
            sel_title = eng_title or original_title or f"Unknown {result.media_type.capitalize()}"
        result = SearchResult(
            id=str(result.id),
            title=sel_title,
            titles=SearchResultTitle(
                english=eng_title,
                romanized=None,
                native=original_title,
            ),
            format=_coerce_tmdb_format(result.media_type),
            season=None,
            year=result.year or -1,
            cover_url=result.poster_url,
            count=None,
            source=SearchSourceTypeGQL.TMDB,
        )
        parsed_results.append(result)
    return SearchResults(count=len(parsed_results), results=parsed_results)


@gql.type
class QuerySearch:
    @gql.field(description="Search using Anilist API")
    async def anilist(
        self,
        info: Info[SessionQLContext, None],
        query: str,
        type: SearchExternalTypeGQL,
        title_sort: SearchTitleTypeGQL = SearchTitleTypeGQL.ENGLISH,
    ) -> Union[SearchResults, Result]:
        # Need to be authorized to use this
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        return await do_anilist_search(query, type, title_sort)

    @gql.field(description="Search using TMDb API")
    async def tmdb(
        self,
        info: Info[SessionQLContext, None],
        query: str,
        title_sort: SearchTitleTypeGQL = SearchTitleTypeGQL.ENGLISH,
    ) -> Union[SearchResults, Result]:
        # Need to be authorized to use this
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        try:
            get_tmdb_client()
        except ShowtimesControllerUninitializedError:
            return Result(success=False, message="TMDb API is not available", code=ErrorCode.TMDbAPIUnavailable)

        return await do_tmdb_search(query, title_sort)
