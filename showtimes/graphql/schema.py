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
from strawberry.file_uploads import Upload
from strawberry.types import Info

from showtimes.extensions.graphql.context import SessionQLContext
from showtimes.extensions.graphql.scalars import UUID as UUIDGQL
from showtimes.extensions.graphql.scalars import Upload as UploadGQL

from .models import Result, UserGQL
from .mutations import mutate_login_user

__all__ = ("make_schema",)


class _SchemaParam(TypedDict):
    query: Type
    mutation: Type | None
    subscription: Type | None


@gql.type
class Query:
    @gql.field(description="Get the current user")
    async def user(self, info: Info[SessionQLContext, None]) -> UserGQL | None:
        if info.context.user is None:
            raise Exception("You are not logged in")
        # return info.context.user
        ...

    @gql.field(description="Get the current or requested server")
    async def server(self, info: Info[SessionQLContext, None], id: UUID | None = gql.UNSET) -> UserGQL | Result:
        if info.context.user is None:
            raise Exception("You are not logged in")

        if id is not None:
            ...  # Check if user is in server

        if id is None and info.context.user.active is not None:
            # Get active server
            ...

        return Result(
            success=False,
            message="You must specify a server ID or set an active server by `mutation { activeServer }`",
        )


@gql.type
class Mutation:
    @gql.mutation(description="Login to Showtimes")
    async def login_user(self, email: str, password: str, info: Info[SessionQLContext, None]) -> Union[UserGQL, Result]:
        if info.context.user is not None:
            return Result(success=False, message="You are already logged in")
        success, user = await mutate_login_user(email, password)
        if not success and isinstance(user, str):
            return Result(success=False, message=user)
        user_info = cast(UserGQL, user)
        info.context.session_latch = True
        info.context.user = user_info.to_session()
        return user_info


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
