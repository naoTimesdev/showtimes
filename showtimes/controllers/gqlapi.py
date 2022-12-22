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

import asyncio
import logging
import traceback
from dataclasses import dataclass
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    Tuple,
    TypedDict,
    TypeVar,
    cast,
)

import aiohttp

from .._metadata import __version__
from ..models.abstract import AttributeDict
from ..utils import complex_walk

__all__ = ("GraphQLResult", "GraphQLPaginationInfo", "GraphQLClient")
ResultT = TypeVar("ResultT", bound="AttributeDict")
PredicateSyncFunc = Callable[[Optional[ResultT]], Tuple[bool, Optional[str], Optional[str]]]
PredicateAwaitFunc = Callable[[Optional[ResultT]], Awaitable[Tuple[bool, Optional[str], Optional[str]]]]
PredicateFunc = PredicateSyncFunc | PredicateAwaitFunc


class GraphQLQueryParam(TypedDict, total=False):
    query: str
    variables: dict[str, Any]
    operationName: str


class GraphQLErrorLocationDict(TypedDict, total=False):
    column: int
    line: int


class GraphQLErrorDict(TypedDict):
    message: str
    locations: list[GraphQLErrorLocationDict]
    path: list[str | int]
    extensions: dict[str, Any]


@dataclass
class GraphQLErrorLocation:
    line: int
    column: int


@dataclass
class GraphQLError:
    message: str
    location: Optional[GraphQLErrorLocation] = None
    code: Optional[str] = None


@dataclass
class GraphQLResult(Generic[ResultT]):
    query: str
    operationName: Optional[str] = None
    data: Optional[ResultT] = None
    errors: Optional[List[GraphQLError]] = None
    httpcode: Optional[int] = None


@dataclass
class GraphQLPaginationInfo:
    hasMore: bool = False
    nextCursor: Optional[Any] = None


class GraphQLClient(Generic[ResultT]):
    def __init__(self, endpoint: str, session: Optional[aiohttp.ClientSession] = None):
        self.endpoint = endpoint
        self.logger = logging.getLogger("http.GraphQLClient")

        self._outside_session = True
        self._sesi: aiohttp.ClientSession = session or aiohttp.ClientSession(
            headers={"User-Agent": f"Showtimes/v{__version__} (https://github.com/naoTimesdev/showtimes)"}
        )
        if session is None:
            self._outside_session = False

    def _convert_data(self, data: Optional[ResultT]):
        if data is None:
            return None
        return AttributeDict(data)

    async def query(
        self, query: str, variables: dict = {}, operation_name: Optional[str] = None
    ) -> GraphQLResult[ResultT]:
        """Send query to the GraphQL API and get the result
        :param query: The query
        :type query: str
        :param variables: The variables, defaults to {}
        :type variables: dict, optional
        :param operation_name: The operation name, defaults to None
        :type operation_name: str, optional
        :return: The request result
        :rtype: GraphQLResult
        """
        query_send: GraphQLQueryParam = {"query": query}
        if len(variables.keys()) > 0:
            query_send["variables"] = variables
        if isinstance(operation_name, str) and len(operation_name.strip()) > 0:
            query_send["operationName"] = operation_name
        async with self._sesi.post(self.endpoint, json=query_send) as resp:
            try:
                json_data = await resp.json()
                get_data = cast(Any, complex_walk(json_data, "data"))
                errors = cast(list[GraphQLErrorDict], complex_walk(json_data, "errors"))
                if not isinstance(errors, list):
                    errors = []
                all_errors = []
                for error in errors:
                    msg = error.get("message", "")
                    error_loc = cast(GraphQLErrorLocationDict | None, complex_walk(cast(dict, error), "locations.0"))
                    if error_loc is not None:
                        error_loc = GraphQLErrorLocation(error_loc.get("line", -1), error_loc.get("column", -1))
                    stack_code = cast(Optional[str], complex_walk(cast(dict, error), "extensions.code"))
                    all_errors.append(GraphQLError(msg, error_loc, stack_code))
                return GraphQLResult(query, operation_name, self._convert_data(get_data), all_errors, resp.status)
            except Exception:
                self.logger.error("An exception occured!\n%s", traceback.format_exc())
                return GraphQLResult(
                    query, operation_name, None, [GraphQLError("Failed to parse JSON file", code="50000")]
                )

    async def _execute_predicate(
        self, predicate: PredicateFunc, content: Optional[ResultT] = None
    ) -> Tuple[bool, str | None, str | None]:
        """Execute the predicate function and return the result"""
        real_func = cast(PredicateFunc, getattr(predicate, "func", predicate))
        if asyncio.iscoroutinefunction(real_func):
            return await real_func(content)
        return cast(PredicateSyncFunc, real_func)(content)  # type guard not working properly

    async def paginate(
        self, query: str, predicate: PredicateFunc, variables: dict = {}, operation_name: Optional[str] = None
    ) -> AsyncGenerator[Tuple[GraphQLResult[ResultT], GraphQLPaginationInfo], None]:
        has_more, next_cursor, cursor_var = await self._execute_predicate(predicate, None)
        has_more = True
        while has_more:
            if next_cursor is not None:
                variables[cursor_var] = next_cursor
            query_request = await self.query(query, variables, operation_name)
            if query_request.data is None:
                has_more = False
            else:
                has_more, next_cursor, _ = await self._execute_predicate(predicate, query_request.data)
            page_info = GraphQLPaginationInfo(has_more, next_cursor)
            yield query_request, page_info

    async def close(self):
        if not self._outside_session:
            await self._sesi.close()
