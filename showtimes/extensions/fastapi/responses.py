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

from typing import Any, Generic, Optional, TypeVar

import orjson
from beanie import PydanticObjectId
from bson import ObjectId
from fastapi.responses import JSONResponse
from pendulum.datetime import DateTime
from pendulum.time import Time
from pydantic import BaseModel, ConfigDict

DataType = TypeVar("DataType")

__all__ = (
    "ORJsonEncoder",
    "ORJSONXResponse",
    "ResponseType",
)


def ORJsonEncoder(obj: Any):  # noqa: N802
    if isinstance(obj, DateTime):
        return obj.for_json()
    if isinstance(obj, Time):
        return obj.for_json()
    if isinstance(obj, (ObjectId, PydanticObjectId)):
        return str(obj)
    raise TypeError


class ORJSONXResponse(JSONResponse):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        return orjson.dumps(
            content,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
            default=ORJsonEncoder,
        )


class ResponseType(BaseModel, Generic[DataType]):
    error: str = "Success"
    code: int = 200
    data: Optional[DataType] = None

    def to_orjson(self, status: int = 200):
        return ORJSONXResponse(self.dict(), status_code=status)

    def to_string(self):
        data = self.dict()
        return orjson.dumps(data, default=ORJsonEncoder, option=orjson.OPT_INDENT_2 | orjson.OPT_SERIALIZE_UUID).decode(
            "utf-8"
        )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "data": None,
                "error": "Success",
                "code": 200,
            }
        }
    )
