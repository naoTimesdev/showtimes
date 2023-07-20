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

from typing import Literal, Tuple, TypeVar, Union

from showtimes.controllers.security import verify_password
from showtimes.graphql.models import UserGQL
from showtimes.models.database import ShowtimesUser

ResultT = TypeVar("ResultT")
ResultOrT = Union[Tuple[Literal[False], str], Tuple[Literal[True], ResultT]]
__all__ = (
    "ResultT",
    "ResultOrT",
    "mutate_login_user",
)


async def mutate_login_user(
    username: str,
    password: str,
) -> ResultOrT[UserGQL]:
    user = await ShowtimesUser.find_one(ShowtimesUser.username == username)
    if not user:
        return False, "User with associated email not found"
    if user.password is None:
        return False, "User has no password set!"

    is_verify, new_password = await verify_password(password, user.password)
    if not is_verify:
        return False, "Password is not correct"
    if new_password is not None and user is not None:
        user.password = new_password
        await user.save_changes()  # type: ignore
    return True, UserGQL.from_db(user)
