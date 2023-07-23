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

from showtimes.graphql.models.fallback import ErrorCode
from showtimes.models.database import ShowtimesServer

__all__ = ("resolve_server_fetch",)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]


async def resolve_server_fetch(srv_id: str) -> ResultOrT[ShowtimesServer]:
    srv_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == UUID(srv_id))
    if not srv_info:
        return False, "Server not found", ErrorCode.ServerNotFound

    return True, srv_info, None
