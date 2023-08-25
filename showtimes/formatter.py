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

from string import Formatter
from typing import Any

__all__ = ("OptionalFormatter",)


class _OptinalDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class OptionalFormatter:
    def __init__(self, data: dict[str, Any]) -> None:
        self.fmt = Formatter()
        self.data = _OptinalDict(data)

    @classmethod
    def format(cls, text: str, **kwargs: Any):
        formatter = cls(kwargs)
        return formatter.fmt.vformat(text, (), formatter.data)
