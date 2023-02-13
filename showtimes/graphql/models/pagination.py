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

from typing import Generic, List, Optional, TypeVar

import strawberry as gql

__all__ = (
    "Connection",
    "PageInfo",
    "ResultType",
    "SortDirection",
)
ResultType = TypeVar("ResultType")


@gql.type
class Connection(Generic[ResultType]):
    """Represents a paginated relationship between two entities

    This pattern is used when the relationship itself has attributes.
    In a Facebook-based domain example, a friendship between two people
    would be a connection that might have a `friendshipStartTime`
    """

    count: int = gql.field(description="The current data count", name="_total")
    """The current data count"""
    page_info: "PageInfo" = gql.field(description="The current pagination information")
    """The current pagination info"""
    nodes: List["ResultType"] = gql.field(description="List of resolved data")
    """The current data list"""


@gql.type
class PageInfo:
    """Pagination context to navigate objects with cursor-based pagination

    Instead of classic offset pagination via `page` and `limit` parameters,
    here we have a cursor of the last object and we fetch items starting from that one

    Read more at:
        - https://graphql.org/learn/pagination/#pagination-and-edges
        - https://relay.dev/graphql/connections.htm
    """

    total_results: int = gql.field(description="The total data count on all pages")
    """The total data count on all pages"""
    per_page: int = gql.field(description="How much data exist per page")
    """How much data exist per page"""
    next_cursor: Optional[str] = gql.field(description="Next cursor for pagination")
    """Next cursor for pagination"""
    has_next_page: bool = gql.field(description="Whether there is a next page or not")
    """Whether there is a next page or not"""


@gql.enum(description="The sort direction for pagination")
class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"
    ASCENDING = "asc"
    DESCENDING = "desc"
