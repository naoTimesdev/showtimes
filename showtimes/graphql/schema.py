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

from typing import Type, TypedDict, Union, cast
from uuid import UUID

import strawberry as gql
from bson import ObjectId
from strawberry.file_uploads import Upload
from strawberry.types import Info

from showtimes.controllers.sessions.handler import is_master_session
from showtimes.extensions.graphql.context import SessionQLContext
from showtimes.extensions.graphql.scalars import UUID as UUIDGQL
from showtimes.extensions.graphql.scalars import Upload as UploadGQL
from showtimes.graphql.cursor import Cursor
from showtimes.graphql.models.pagination import Connection, SortDirection
from showtimes.graphql.models.projects import ProjectGQL
from showtimes.graphql.models.servers import ServerGQL
from showtimes.models.database import ShowProject, ShowtimesServer, ShowtimesUser, UserType
from showtimes.models.session import ServerSessionInfo

from .models import ErrorCode, Result, UserGQL, UserTemporaryGQL
from .mutations.users import (
    mutate_login_user,
    mutate_migrate_user,
    mutate_migrate_user_approve,
    mutate_register_user,
    mutate_register_user_approve,
    mutate_reset_password,
)
from .queries.search import QuerySearch
from .queries.showtimes import (
    resolve_projects_fetch_paginated,
    resolve_projects_latest_information,
    resolve_server_fetch,
    resolve_server_project_fetch,
    resolve_servers_fetch_paginated,
)

__all__ = ("make_schema",)


class _SchemaParam(TypedDict):
    query: Type
    mutation: Type | None
    subscription: Type | None


@gql.type
class Query:
    search: QuerySearch = gql.field(
        description="Do a search on external source or internal database", resolver=QuerySearch
    )

    @gql.field(description="Get current user session, different from user query which query user information")
    async def session(self, info: Info[SessionQLContext, None]):
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

    @gql.field(description="Get current logged in user")
    async def user(self, info: Info[SessionQLContext, None]) -> Union[UserGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        if is_master_session(info.context.user):
            # If master session, return temporary info
            return UserGQL(
                id=info.context.user.session_id,
                username=info.context.user.username,
                privilege=UserType.ADMIN,
                avatar=None,
                user_id=info.context.user.user_id,
                discord_meta=None,
            )

        user_info = await ShowtimesUser.find_one(ShowtimesUser.id == ObjectId(info.context.user.object_id))
        if user_info is None:
            info.context.session_latch = True
            info.context.user = None
            return Result(success=False, message="User not found", code=ErrorCode.UserNotFound)

        return UserGQL.from_db(user_info)

    @gql.field(description="Get server info")
    async def server(self, info: Info[SessionQLContext, None], id: UUID | None = None) -> Union[ServerGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        srv_id = None
        if info.context.user.active is not None:
            srv_id = info.context.user.active.server_id
        if id is not None:
            srv_id = str(id)

        if srv_id is None:
            return Result(
                success=False,
                message="No server selected, either use mutation selectServer or add id param to this query",
                code=ErrorCode.ServerUnselect,
            )

        success, srv_info, err_code = await resolve_server_fetch(srv_id)
        if not success and isinstance(srv_info, str):
            return Result(success=False, message=srv_info, code=err_code)

        srv_cast = ServerGQL.from_db(cast(ShowtimesServer, srv_info))
        return srv_cast

    @gql.field(description="Get all servers with pagination")
    async def servers(
        self,
        info: Info[SessionQLContext, None],
        ids: list[UUID] | None = gql.UNSET,
        limit: int = 10,
        cursor: Cursor | None = gql.UNSET,
        sort: SortDirection = SortDirection.ASC,
    ) -> Connection[ServerGQL] | Result:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        return await resolve_servers_fetch_paginated(ids, limit, cursor, sort)

    @gql.field(description="Get server project info")
    async def project(
        self, info: Info[SessionQLContext, None], id: UUID, server_id: UUID | None = gql.UNSET
    ) -> Union[ProjectGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        srv_id = None
        if info.context.user.active is not None:
            srv_id = info.context.user.active.server_id
        if id is not None:
            srv_id = str(server_id)

        if srv_id is None:
            return Result(
                success=False,
                message="No server selected, either use mutation selectServer or add id param to this query",
                code=ErrorCode.ServerUnselect,
            )

        success, srv_info, err_code = await resolve_server_project_fetch(
            str(id),
            str(srv_id),
        )
        if not success and isinstance(srv_info, str):
            return Result(success=False, message=srv_info, code=err_code)

        srv_cast = ProjectGQL.from_db(cast(ShowProject, srv_info))
        return srv_cast

    @gql.field(description="Get all projects with pagination")
    async def projects(
        self,
        info: Info[SessionQLContext, None],
        ids: list[UUID] | None = gql.UNSET,
        limit: int = 10,
        cursor: Cursor | None = gql.UNSET,
        sort: SortDirection = SortDirection.ASC,
    ) -> Connection[ProjectGQL] | Result:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        return await resolve_projects_fetch_paginated(ids, limit, cursor, sort)

    @gql.field(description="Get latest progress for all projects with pagination")
    async def latests(
        self,
        info: Info[SessionQLContext, None],
        id: UUID | None = gql.UNSET,
        limit: int = 10,
        cursor: Cursor | None = gql.UNSET,
        sort: SortDirection = SortDirection.ASC,
    ) -> Result | Connection[ProjectGQL]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        srv_id = None
        if info.context.user.active is not None:
            srv_id = UUID(info.context.user.active.server_id)
        if isinstance(id, UUID):
            srv_id = id

        if srv_id is None:
            return Result(
                success=False,
                message="No server selected, either use mutation selectServer or add id param to this query",
                code=ErrorCode.ServerUnselect,
            )

        return await resolve_projects_latest_information(srv_id, limit, cursor, sort)


@gql.type
class Mutation:
    @gql.mutation(description="Login to Showtimes")
    async def login(self, username: str, password: str, info: Info[SessionQLContext, None]) -> Union[UserGQL, Result]:
        if info.context.user is not None:
            return Result(success=False, message="You are already logged in", code=ErrorCode.SessionExist)
        success, user, code = await mutate_login_user(username, password)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=code)
        user_info = cast(UserGQL, user)
        info.context.session_latch = True
        info.context.user = user_info.to_session()
        return user_info

    @gql.mutation(description="Register to Showtimes")
    async def register(
        self, username: str, password: str, info: Info[SessionQLContext, None]
    ) -> Union[UserTemporaryGQL, Result]:
        if info.context.user is not None:
            return Result(success=False, message="You are already logged in", code=ErrorCode.SessionExist)
        success, user, code = await mutate_register_user(username, password)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=code)
        user_info = cast(UserTemporaryGQL, user)
        return user_info

    @gql.mutation(description="Approve a user registration")
    async def approve_register(
        self, username: str, password: str, code: str, info: Info[SessionQLContext, None]
    ) -> Union[UserGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        if not is_master_session(info.context.user):
            return Result(
                success=False,
                message="You are not allowed to approve a user registration",
                code=ErrorCode.SessionNotMaster,
            )

        success, user, err_code = await mutate_register_user_approve(username, password, code)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=err_code)
        user_info = cast(UserGQL, user)
        return user_info

    @gql.mutation(description="Migrate user to new Showtimes")
    async def migrate(
        self, username: str, password: str, info: Info[SessionQLContext, None]
    ) -> Union[UserTemporaryGQL, Result]:
        if info.context.user is not None:
            return Result(success=False, message="You are already logged in", code=ErrorCode.SessionExist)
        success, user, code = await mutate_migrate_user(username, password)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=code)
        user_info = cast(UserTemporaryGQL, user)
        return user_info

    @gql.mutation(description="Approve a user migration request")
    async def approve_migration(
        self, username: str, password: str, code: str, info: Info[SessionQLContext, None]
    ) -> Union[UserGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)

        if not is_master_session(info.context.user):
            return Result(
                success=False,
                message="You are not allowed to approve a user registration",
                code=ErrorCode.SessionNotMaster,
            )

        success, user, err_code = await mutate_migrate_user_approve(username, password, code)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=err_code)
        user_info = cast(UserGQL, user)
        return user_info

    @gql.mutation(description="Logout from Showtimes")
    async def logout(self, info: Info[SessionQLContext, None]) -> Result:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)
        info.context.session_latch = True
        info.context.user = None
        return Result(success=True, message=None, code=None)

    @gql.mutation(description="Reset password of an account")
    async def reset_password(
        self, old_password: str, new_password: str, info: Info[SessionQLContext, None]
    ) -> Union[UserGQL, Result]:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)
        success, user, code = await mutate_reset_password(UUID(info.context.user.user_id), old_password, new_password)
        if not success and isinstance(user, str):
            return Result(success=False, message=user, code=code)
        user_info = cast(UserGQL, user)
        info.context.session_latch = True
        info.context.user = user_info.to_session()
        return user_info

    @gql.mutation(description="Select or deselect an active server for an account")
    async def select_server(self, info: Info[SessionQLContext, None], id: UUID | None = None) -> Result:
        if info.context.user is None:
            return Result(success=False, message="You are not logged in", code=ErrorCode.SessionUnknown)
        if id is None:
            info.context.user.active = None
            info.context.session_latch = True
            return Result(success=True, message=None, code=None)

        success, srv_info, err_code = await resolve_server_fetch(str(id))
        if not success and isinstance(srv_info, str):
            return Result(success=False, message=srv_info, code=err_code)
        srv_info = cast(ShowtimesServer, srv_info)
        owner_ref_ids = [str(i.ref.id) for i in srv_info.owners]
        if info.context.user.privilege != UserType.ADMIN and info.context.user.object_id not in owner_ref_ids:
            return Result(
                success=False, message="You are not one of the owner of this server", code=ErrorCode.ServerNotAllowed
            )
        info.context.session_latch = True
        info.context.user.active = ServerSessionInfo(server_id=str(srv_info.server_id), name=srv_info.name)
        return Result(success=True, message=None, code=None)


@gql.type
class Subscription:
    ...


def _has_any_function_or_attr(obj: type | object) -> bool:
    any_function = any((callable(getattr(obj, name, None)) for name in dir(obj) if not name.startswith("_")))
    annotations = getattr(obj, "__annotations__", None)
    any_attr = annotations is not None and len(annotations) > 0
    return any_function or any_attr


def make_schema() -> gql.Schema:
    _schema_params: _SchemaParam = {
        "query": Query,
        "mutation": None,
        "subscription": None,
    }
    if _has_any_function_or_attr(Mutation):
        _schema_params["mutation"] = Mutation
    if _has_any_function_or_attr(Subscription):
        _schema_params["subscription"] = Subscription
    return gql.Schema(
        **_schema_params,
        scalar_overrides={
            UUID: UUIDGQL,
            Upload: UploadGQL,
        },
    )
