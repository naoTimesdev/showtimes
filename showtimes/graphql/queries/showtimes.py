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

import asyncio
from typing import Literal, TypeAlias, TypeVar
from uuid import UUID

import strawberry as gql
from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn
from bson import ObjectId

from showtimes.graphql.cursor import Cursor, parse_cursor, to_cursor
from showtimes.graphql.models.common import KeyValueGQL
from showtimes.graphql.models.fallback import ErrorCode, NodeResult, Result
from showtimes.graphql.models.pagination import Connection, PageInfo, SortDirection
from showtimes.graphql.models.projects import ProjectGQL
from showtimes.graphql.models.servers import ServerGQL
from showtimes.models.database import ShowProject, ShowtimesServer
from showtimes.tooling import get_logger

__all__ = (
    "resolve_server_fetch",
    "resolve_servers_fetch_paginated",
    "resolve_server_project_fetch",
    "resolve_projects_fetch_paginated",
    "resolve_projects_latest_information",
    "resolve_server_statistics",
)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]
logger = get_logger("Showtimes.GraphQL.Query.Showtimes")


async def resolve_server_fetch(srv_id: str, owner_id: str | None = None) -> ResultOrT[ShowtimesServer]:
    logger.info(f"Fetching server {srv_id} with owner {owner_id}")
    srv_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == UUID(srv_id))
    if not srv_info:
        logger.warning(f"Server {srv_id} not found")
        return False, "Server not found", ErrorCode.ServerNotFound

    object_owners: list[ObjectId] = [owner.ref.id for owner in srv_info.owners]
    if owner_id is not None and ObjectId(owner_id) not in object_owners:
        logger.warning(f"User {owner_id} is not one of the owner of server {srv_id}")
        return False, "You are not one of the owner of this server", ErrorCode.ServerNotAllowed

    return True, srv_info, None


async def resolve_servers_fetch_paginated(
    ids: list[UUID] | None = gql.UNSET,
    limit: int = 20,
    cursor: Cursor | None = gql.UNSET,
    sort: SortDirection = SortDirection.ASC,
    owner_id: str | None = gql.UNSET,
) -> Connection[ServerGQL]:
    act_limit = limit + 1
    direction = "-" if sort is SortDirection.DESCENDING else "+"

    cursor_id = parse_cursor(cursor)
    logger.info(f"Fetching servers with cursor {cursor_id} | limit {act_limit} | sort {sort} | owner ID {owner_id}")
    find_args = []
    if owner_id is not None:
        find_args.append(OpIn("owners.$id", [ObjectId(owner_id)]))
    if isinstance(ids, list):
        logger.info(f"Fetching servers with IDs {ids}")
        find_args.append(OpIn(ShowtimesServer.server_id, ids))
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
        logger.warning("No results found from query, returning empty connection")
        return Connection(
            count=0,
            page_info=PageInfo(total_results=0, per_page=limit, next_cursor=None, has_next_page=False),
            nodes=[],
        )

    query_count = []
    if owner_id is not None:
        query_count.append(find_args[0])
    if isinstance(ids, list):
        query_count.append(OpIn(ShowtimesServer.server_id, ids))

    logger.info(f"Fetching servers count with query {query_count}")
    items_count = await ShowtimesServer.find(*query_count).count()

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
    logger.info(f"Fetching project {project_id} on server {srv_id}")
    proj_info = await ShowProject.find_one(
        OpAnd(
            ShowProject.server_id == UUID(srv_id),  # type: ignore
            ShowProject.show_id == UUID(project_id),  # type: ignore
        )
    )
    if not proj_info:
        logger.error(f"Project {project_id} not found on server {srv_id}")
        return False, "Project not found on specified server", ErrorCode.ProjectNotFound

    return True, proj_info, None


async def resolve_projects_fetch_paginated(
    ids: list[UUID] | None = gql.UNSET,
    server_ids: list[UUID] | None = gql.UNSET,
    limit: int = 20,
    cursor: Cursor | None = gql.UNSET,
    sort: SortDirection = SortDirection.ASC,
) -> Connection[ProjectGQL]:
    act_limit = limit + 1
    direction = "-" if sort is SortDirection.DESCENDING else "+"

    cursor_id = parse_cursor(cursor)
    find_args = []
    count_args = []
    if isinstance(ids, list):
        find_args.append(OpIn(ShowProject.show_id, ids))
        count_args.append(OpIn(ShowProject.show_id, ids))
    if isinstance(server_ids, list):
        find_args.append(OpIn(ShowProject.server_id, server_ids))
        count_args.append(OpIn(ShowProject.server_id, server_ids))
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

    items_count = await ShowProject.find(*count_args).count()

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
    include_last: bool = False,
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

    mapped_items = [ProjectGQL.from_db(item, only_latest=True, include_last=include_last) for item in items]
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


def _calculate_server_statistics(projects: list[ShowProject]) -> list[KeyValueGQL[int]]:
    unfinished = 0
    finished = 0
    for project in projects:
        if all(episode.is_released for episode in project.statuses):
            finished += 1
        else:
            unfinished += 1
    return [
        KeyValueGQL(key="STATS_UNFINISHED", value=unfinished),
        KeyValueGQL(key="STATS_FINISHED", value=finished),
        KeyValueGQL(key="STATS_TOTAL", value=len(projects)),
    ]


async def resolve_server_statistics(
    server_id: UUID,
) -> Result | NodeResult[KeyValueGQL[int]]:
    server = await ShowtimesServer.find_one(ShowtimesServer.server_id == server_id)
    if not server:
        return Result(success=False, message="Server not found", code=ErrorCode.ServerNotFound)
    projects = await ShowProject.find(ShowProject.server_id == server_id).to_list()

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _calculate_server_statistics, projects)
    results.append(KeyValueGQL(key="STATS_OWNERS", value=len(server.owners)))
    return NodeResult(nodes=results)
