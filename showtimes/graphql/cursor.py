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

from base64 import b64decode, b64encode
from typing import Optional, TypeAlias

import strawberry as gql
from bson import ObjectId
from bson.errors import InvalidId

from showtimes.graphql.exceptions import InvalidCursor, UnknownCursorFormat

__all__ = (
    "Cursor",
    "parse_cursor",
    "to_cursor",
)
Cursor: TypeAlias = str


def _decode_cursor(cursor: Cursor):
    try:
        decoded = b64decode(cursor).decode("utf-8")
    except Exception as e:
        raise UnknownCursorFormat(cursor) from e
    if not decoded.startswith("cursor_"):
        raise UnknownCursorFormat(cursor)
    return decoded[7:]


def _encode_cursor(obj_id: ObjectId):
    str_obj = "cursor_" + str(obj_id)
    return b64encode(str_obj.encode("utf-8")).decode("utf-8")


def parse_cursor(cursor: Optional[Cursor]) -> Optional[ObjectId]:
    if cursor is None:
        return None
    if cursor is gql.UNSET:
        return None
    dec_cursor = _decode_cursor(cursor)
    try:
        return ObjectId(dec_cursor)
    except (TypeError, InvalidId) as exc:
        raise InvalidCursor(cursor) from exc


def to_cursor(obj_id: Optional[ObjectId]) -> Optional[Cursor]:
    return _encode_cursor(obj_id) if obj_id is not None else None
