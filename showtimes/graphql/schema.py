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

from typing import Optional, Type, TypedDict
from uuid import UUID

import strawberry as gql
from strawberry.file_uploads import Upload

from showtimes.extensions.graphql.scalars import UUID as UUIDGQL
from showtimes.extensions.graphql.scalars import Upload as UploadGQL

__all__ = ("make_schema",)


class _SchemaParam(TypedDict):
    query: Type
    mutation: Type | None
    subscription: Type | None


@gql.type(description="Simple result of mutation")
class Result:
    success: bool = gql.field(description="Success status")
    message: Optional[str] = gql.field(description="Extra message if any, might be available if success is False")


@gql.type
class Query:
    ...


@gql.type
class Mutation:
    ...


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
