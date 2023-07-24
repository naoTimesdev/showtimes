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

from typing import Literal, TypeAlias, TypeVar
from uuid import UUID

import strawberry as gql
from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn

from showtimes.graphql.cursor import Cursor, parse_cursor, to_cursor
from showtimes.graphql.models.fallback import ErrorCode
from showtimes.graphql.models.pagination import Connection, PageInfo, SortDirection
from showtimes.graphql.models.projects import ProjectGQL
from showtimes.graphql.models.servers import ServerGQL
from showtimes.models.database import ShowProject, ShowtimesServer

__all__ = (
    "resolve_server_fetch",
    "resolve_servers_fetch_paginated",
    "resolve_server_project_fetch",
    "resolve_projects_fetch_paginated",
    "resolve_projects_latest_information",
)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]


async def resolve_server_fetch(srv_id: str) -> ResultOrT[ShowtimesServer]:
    srv_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == UUID(srv_id))
    if not srv_info:
        return False, "Server not found", ErrorCode.ServerNotFound

    return True, srv_info, None


async def resolve_servers_fetch_paginated(
    ids: list[UUID] | None = gql.UNSET,
    limit: int = 20,
    cursor: Cursor | None = gql.UNSET,
    sort: SortDirection = SortDirection.ASC,
) -> Connection[ServerGQL]:
    act_limit = limit + 1
    direction = "-" if sort is SortDirection.DESCENDING else "+"

    cursor_id = parse_cursor(cursor)
    find_args = []
    added_query_ids = False
    if isinstance(ids, list):
        find_args.append(OpIn(ShowtimesServer.server_id, ids))
        added_query_ids = True
    if cursor_id is not None:
        find_args.append(ShowtimesServer.id >= cursor_id)

    items = (
        await ShowtimesServer.find(
            *find_args,
        )
        .sort(f"{direction}_id")
        .limit(act_limit)
        .to_list()
    )
    if len(items) < 1:
        return Connection(
            count=0,
            page_info=PageInfo(total_results=0, per_page=limit, next_cursor=None, has_next_page=False),
            nodes=[],
        )

    if added_query_ids:
        items_count = await ShowtimesServer.find(find_args[0]).count()
    else:
        items_count = await ShowtimesServer.find().count()

    last_item = None
    if len(items) > limit:
        last_item = items.pop()

    next_cursor = last_item.id if last_item is not None else None
    has_next_page = next_cursor is not None

    mapped_items = [ServerGQL.from_db(item) for item in items]
    return Connection(
        count=len(mapped_items),
        page_info=PageInfo(
            total_results=items_count,
            per_page=limit,
            next_cursor=to_cursor(next_cursor),
            has_next_page=has_next_page,
        ),
        nodes=mapped_items,
    )


async def resolve_server_project_fetch(srv_id: str, project_id: str) -> ResultOrT[ShowProject]:
    proj_info = await ShowProject.find_one(
        OpAnd(
            ShowProject.server_id == UUID(srv_id),  # type: ignore
            ShowProject.show_id == UUID(project_id),  # type: ignore
        )
    )
    if not proj_info:
        return False, "Project not found on specified server", ErrorCode.ProjectNotFound

    return True, proj_info, None


async def resolve_projects_fetch_paginated(
    ids: list[UUID] | None = gql.UNSET,
    limit: int = 20,
    cursor: Cursor | None = gql.UNSET,
    sort: SortDirection = SortDirection.ASC,
) -> Connection[ProjectGQL]:
    act_limit = limit + 1
    direction = "-" if sort is SortDirection.DESCENDING else "+"

    cursor_id = parse_cursor(cursor)
    find_args = []
    added_query_ids = False
    if isinstance(ids, list):
        find_args.append(OpIn(ShowProject.show_id, ids))
        added_query_ids = True
    if cursor_id is not None:
        find_args.append(ShowProject.id >= cursor_id)

    items = (
        await ShowProject.find(
            *find_args,
        )
        .sort(f"{direction}_id")
        .limit(act_limit)
        .to_list()
    )
    if len(items) < 1:
        return Connection(
            count=0,
            page_info=PageInfo(total_results=0, per_page=limit, next_cursor=None, has_next_page=False),
            nodes=[],
        )

    if added_query_ids:
        items_count = await ShowProject.find(find_args[0]).count()
    else:
        items_count = await ShowProject.find().count()

    last_item = None
    if len(items) > limit:
        last_item = items.pop()

    next_cursor = last_item.id if last_item is not None else None
    has_next_page = next_cursor is not None

    mapped_items = [ProjectGQL.from_db(item) for item in items]
    return Connection(
        count=len(mapped_items),
        page_info=PageInfo(
            total_results=items_count,
            per_page=limit,
            next_cursor=to_cursor(next_cursor),
            has_next_page=has_next_page,
        ),
        nodes=mapped_items,
    )


async def resolve_projects_latest_information(
    id: UUID,
    limit: int = 20,
    cursor: Cursor | None = gql.UNSET,
    sort: SortDirection = SortDirection.ASC,
) -> Connection[ProjectGQL]:
    act_limit = limit + 1
    direction = "-" if sort is SortDirection.DESCENDING else "+"

    cursor_id = parse_cursor(cursor)
    find_args = [ShowProject.server_id == id]
    if cursor_id is not None:
        find_args.append(ShowProject.id >= cursor_id)

    items = (
        await ShowProject.find(
            *find_args,
        )
        .sort(f"{direction}_id")
        .limit(act_limit)
        .to_list()
    )
    if len(items) < 1:
        return Connection(
            count=0,
            page_info=PageInfo(total_results=0, per_page=limit, next_cursor=None, has_next_page=False),
            nodes=[],
        )

    items_count = await ShowProject.find(find_args[0]).count()

    last_item = None
    if len(items) > limit:
        last_item = items.pop()

    next_cursor = last_item.id if last_item is not None else None
    has_next_page = next_cursor is not None

    mapped_items = [ProjectGQL.from_db(item, only_latest=True) for item in items]
    return Connection(
        count=len(mapped_items),
        page_info=PageInfo(
            total_results=items_count,
            per_page=limit,
            next_cursor=to_cursor(next_cursor),
            has_next_page=has_next_page,
        ),
        nodes=mapped_items,
    )
