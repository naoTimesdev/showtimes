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

from datetime import datetime
from functools import partial as ftpartial
from typing import ForwardRef, get_args

import pendulum
from beanie import Document
from pendulum.datetime import DateTime
from pendulum.parser import parse as pendulum_parse
from pydantic.typing import resolve_annotations

__all__ = (
    "_coerce_to_pendulum",
    "pendulum_utc",
)
pendulum_utc = ftpartial(pendulum.now, tz="UTC")


def _unpack_forwardref(annotation):
    if isinstance(annotation, ForwardRef):
        return annotation.__forward_arg__
    return annotation


def _coerce_to_pendulum(clss: Document):
    # Some crackhead solution to parse DateTime to pendulum instance
    # Get annotation list, and check if it's DateTime instance
    # If it is, then check if it's a pendulum instance or not

    annotations = clss.__annotations__
    annotate = resolve_annotations(annotations, None)

    for key, type_t in annotate.items():
        act_type = type_t
        type_arg = get_args(type_t)
        if len(type_arg) > 0:
            act_type = type_arg[0]
        fwd_unpack = _unpack_forwardref(act_type)

        try:
            is_pdt_type = issubclass(act_type, DateTime) or "pendulum.DateTime" in str(fwd_unpack)
        except Exception:
            is_pdt_type = "pendulum.DateTime" in str(fwd_unpack)
            if not is_pdt_type:
                continue

        # check if it's pendulum class type
        if is_pdt_type:
            # Coerce to pendulum instance
            current = object.__getattribute__(clss, key)
            if current is None:
                continue
            if isinstance(current, DateTime):
                continue
            if isinstance(current, str):
                # Assume ISO8601 format
                object.__setattr__(clss, key, pendulum_parse(current))
            elif isinstance(current, (int, float)):
                # Unix timestamp
                object.__setattr__(clss, key, pendulum.from_timestamp(current))
            elif isinstance(current, datetime):
                object.__setattr__(clss, key, pendulum.instance(current))
