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
from uuid import UUID

from showtimes.controllers.security import encrypt_password, verify_password
from showtimes.graphql.models import UserGQL
from showtimes.graphql.models.users import UserRegisterGQL
from showtimes.models.database import ShowtimesUser, ShowtimesUserRegister, UserType

ResultT = TypeVar("ResultT")
ResultOrT = Union[Tuple[Literal[False], str], Tuple[Literal[True], ResultT]]
__all__ = (
    "ResultT",
    "ResultOrT",
    "mutate_login_user",
    "mutate_register_user",
    "mutate_register_user_approve",
    "mutate_reset_password",
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


async def mutate_register_user(
    username: str,
    password: str,
) -> ResultOrT[UserRegisterGQL]:
    user = await ShowtimesUser.find_one(ShowtimesUser.username == username)
    if user:
        return False, "User already exists"

    regist_user = await ShowtimesUserRegister.find_one(ShowtimesUserRegister.username == username)
    if regist_user:
        return True, UserRegisterGQL.from_db(regist_user)

    regist_user = ShowtimesUserRegister(
        username=username,
        password=await encrypt_password(password),
    )

    await regist_user.save()  # type: ignore
    return True, UserRegisterGQL.from_db(regist_user)


async def mutate_register_user_approve(
    username: str,
    password: str,
    approval_code: str,
) -> ResultOrT[UserGQL]:
    user = await ShowtimesUserRegister.find_one(ShowtimesUserRegister.username == username)
    if not user:
        return False, "User not found"

    if user.approval_code != approval_code:
        return False, "Approval code is not correct"

    is_verify, _ = await verify_password(password, user.password)
    if not is_verify:
        return False, "Password is not correct"

    new_user = ShowtimesUser(
        username=user.username,
        privilege=UserType.USER,
        password=user.password,
        user_id=user.user_id,
    )

    await new_user.save()  # type: ignore
    await user.delete()  # type: ignore

    return True, UserGQL.from_db(new_user)


async def mutate_reset_password(
    user_id: UUID,
    old_password: str,
    new_password: str,
) -> ResultOrT[UserGQL]:
    user = await ShowtimesUser.find_one(ShowtimesUser.user_id == user_id)
    if not user:
        return False, "User with associated email not found"
    new_pass_hash = await encrypt_password(new_password)
    if user.password is None:
        user.password = new_pass_hash
        await user.save_changes()  # type: ignore
        return True, UserGQL.from_db(user)
    if old_password == new_password:
        return False, "New password cannot be the same as old password"

    is_verify, _ = await verify_password(old_password, user.password)
    if not is_verify:
        return False, "Old password is not correct"

    user.password = new_pass_hash
    await user.save_changes()  # type: ignore
    return True, UserGQL.from_db(user)
