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

from typing import Annotated, Any, Callable

import pendulum
from pendulum.datetime import DateTime
from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

__all__ = ("PydanticDateTime",)


class PydanticPendulumDateTimeAnnotation:
    @classmethod
    def __get_pydantic_core_schema__(
        cls: type[PydanticPendulumDateTimeAnnotation],
        _source_type: Any,
        _handler: Callable[[Any], core_schema.CoreSchema],
    ) -> core_schema.CoreSchema:
        def validate_from_iso(value: Any) -> DateTime:
            return pendulum.instance(value)

        from_iso_schema = core_schema.chain_schema(
            [core_schema.datetime_schema(), core_schema.no_info_plain_validator_function(validate_from_iso)]
        )

        return core_schema.json_or_python_schema(
            json_schema=from_iso_schema,
            python_schema=core_schema.union_schema(
                [
                    core_schema.is_instance_schema(DateTime),
                    from_iso_schema,
                ]
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda dt: dt.to_iso8601_string(),
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # Use the same schema that would be used for `int`
        return handler(core_schema.datetime_schema())


PydanticDateTime = Annotated[DateTime, PydanticPendulumDateTimeAnnotation]
