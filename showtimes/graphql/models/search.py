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

from typing import Optional

import strawberry as gql

from showtimes.graphql.models.enums import SearchExternalTypeGQL, SearchSourceTypeGQL

__all__ = (
    "SearchResultTitle",
    "SearchResult",
    "SearchResults",
)


@gql.type(description="Simple search result from external source")
class SearchResultTitle:
    english: Optional[str] = gql.field(description="English title")
    romanized: Optional[str] = gql.field(description="Romanized title")
    native: Optional[str] = gql.field(description="Native or Original title")


@gql.type(description="Simple search result from external source")
class SearchResult:
    id: str = gql.field(description="The show/book ID of the result")
    title: str = gql.field(description="The title of the result")
    titles: SearchResultTitle = gql.field(description="The titles of the result")
    format: SearchExternalTypeGQL = gql.field(description="The format of the result")
    season: Optional[str] = gql.field(description="The season of the result, only applicable for shows")
    year: Optional[int] = gql.field(description="The starting year of the result")
    cover_url: Optional[str] = gql.field(description="The cover URL of the result")
    count: Optional[int] = gql.field(description="The count of the result")
    source: SearchSourceTypeGQL = gql.field(description="The source of the result")


@gql.type(description="Simple search results from external source")
class SearchResults:
    count: int = gql.field(description="The count of the results")
    results: list[SearchResult] = gql.field(description="The results")
