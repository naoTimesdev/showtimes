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

import asyncio
import re
from typing import Literal, Tuple, TypeVar, Union, cast
from uuid import UUID

from showtimes.controllers.searcher import get_searcher
from showtimes.controllers.security import encrypt_password, verify_password
from showtimes.graphql.models import UserGQL
from showtimes.graphql.models.common import IntegrationInputGQL
from showtimes.graphql.models.enums import IntegrationInputActionGQL
from showtimes.graphql.models.fallback import ErrorCode
from showtimes.graphql.models.users import UserTemporaryGQL
from showtimes.models.database import (
    IntegrationId,
    ShowtimesTemporaryUser,
    ShowtimesTempUserType,
    ShowtimesUser,
    ShowtimesUserGroup,
    UserType,
)
from showtimes.models.searchdb import UserSearch
from showtimes.tooling import get_logger

__all__ = (
    "ResultT",
    "ResultOrT",
    "mutate_login_user",
    "mutate_register_user",
    "mutate_migrate_user",
    "mutate_migrate_user_approve",
    "mutate_reset_password",
    "mutate_user_bind_integrations",
)
ResultT = TypeVar("ResultT")
ResultOrT = Union[Tuple[Literal[False], str, str], Tuple[Literal[True], ResultT, None]]
logger = get_logger("Showtimes.GraphQL.Mutations.Users")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9\.\-\_]+$", re.I)


async def update_searchdb(user: ShowtimesUser) -> None:
    logger.debug(f"Updating User Search Index for user {user.user_id}")
    searcher = get_searcher()
    await searcher.update_document(UserSearch.from_db(user))


async def mutate_login_user(
    username: str,
    password: str,
) -> ResultOrT[ShowtimesUser]:
    logger.info(f"Logging in as {username}")
    user = await ShowtimesUserGroup.find_one(ShowtimesUserGroup.username == username, with_children=True)
    if not user:
        logger.warning(f"User {username} not found")
        return False, "User with associated username not found", ErrorCode.UserNotFound
    if user.is_temp_user():
        logger.warning(f"User {username} is temporary user")
        return False, "User is temporary user, please do password reset first", ErrorCode.UserMigrate
    user = cast(ShowtimesUser, user)
    if user.password is None:
        logger.warning(f"User {username} has no password set")
        if user.discord_meta is not None:
            logger.warning(f"User {username} has discord meta, returning it")
            return False, "Please use Discord to login, or do password reset first", ErrorCode.UserDiscordMigrate
        return False, "User has no password set, please do password reset first", ErrorCode.UserMigrate

    is_verify, new_password = await verify_password(password, user.password)
    if not is_verify:
        logger.warning(f"User {username} password is not correct")
        return False, "Password is not correct", ErrorCode.UserInvalidPass
    if new_password is not None and user is not None:
        user.password = new_password
        await user.save_changes()  # type: ignore
    logger.info(f"User {username} authenticated!")
    return True, user, None


async def is_valid_username(username: str) -> bool:
    # Username must be alphanumeric + _, -, and . (similar to Discord new username)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _USERNAME_RE.match, username) is not None


async def mutate_register_user(
    username: str,
    password: str,
) -> ResultOrT[UserGQL]:
    logger.info(f"Registering user {username}")
    existing_user = await ShowtimesUser.find_one(ShowtimesUser.username == username)
    if existing_user:
        logger.warning(f"User {username} already exists")
        return False, "User already exists", ErrorCode.UserAlreadyExist

    if len(password) < 8:
        logger.warning(f"User {username} password is too short")
        return False, "Password must be at least 8 characters long", ErrorCode.UserRequirementPass
    if len(username) < 4:
        logger.warning(f"User {username} username is too short")
        return False, "Username must be at least 4 characters long", ErrorCode.UserRequirementUsernameShort
    if len(username) > 32:
        logger.warning(f"User {username} username is too long")
        return False, "Username must be at most 32 characters long", ErrorCode.UserRequirementUsernameLong
    if not await is_valid_username(username):
        logger.warning(f"User {username} username is invalid")
        return False, "Username must be alphanumeric + _, -, and .", ErrorCode.UserRequirementUsernameInvalid

    regist_user = ShowtimesUser(
        username=username,
        password=await encrypt_password(password),
        privilege=UserType.USER,
    )

    logger.info(f"Saving user {username} to database")
    await regist_user.save()  # type: ignore
    return True, UserGQL.from_db(regist_user), None


async def mutate_migrate_user(
    username: str,
    password: str,
) -> ResultOrT[UserTemporaryGQL]:
    logger.info(f"Migrating user {username}")
    migrate_user = await ShowtimesTemporaryUser.find_one(
        ShowtimesTemporaryUser.username == username,
        ShowtimesTemporaryUser.type == ShowtimesTempUserType.MIGRATION,
    )
    if migrate_user is None:
        logger.warning(f"User {username} has no migration request!")
        return False, "User has no migration request", ErrorCode.UserNotFound

    if len(password) < 8:
        return False, "Password must be at least 8 characters long", ErrorCode.UserRequirementPass

    migrate_user.password = await encrypt_password(password)
    await migrate_user.save()  # type: ignore

    return True, UserTemporaryGQL.from_db(migrate_user), None


async def mutate_migrate_user_approve(
    username: str,
    password: str,
    approval_code: str,
) -> ResultOrT[UserGQL]:
    logger.info(f"Approving migrate user {username}")
    user: ShowtimesTemporaryUser | None = await ShowtimesTemporaryUser.find_one(
        ShowtimesTemporaryUser.username == username,
        ShowtimesTemporaryUser.type == ShowtimesTempUserType.MIGRATION,
    )
    if not user:
        logger.warning(f"User {username} not found")
        return False, "User not found", ErrorCode.UserNotFound

    if user.password.startswith("unset_"):
        logger.warning(f"Migration are not initiated yet for {username}")
        return False, "Migration are not initiated yet for this user", ErrorCode.UserMigrateNotInitiated

    if user.approval_code != approval_code:
        logger.warning(f"User {username} approval code is not correct")
        return False, "Approval code is not correct", ErrorCode.UserApprovalIncorrect
    if not await verify_password(password, user.password):
        logger.warning(f"User {username} password is not correct")
        return False, "Password is not correct", ErrorCode.UserInvalidPass

    new_user = user.to_user(persist=True)
    logger.info(f"Saving user {username} to database")
    await user.delete()  # type: ignore
    _new_user = await ShowtimesUser.insert_one(new_user)
    if not _new_user:
        logger.warning(f"Failed to migrate user {username}")
        return False, "Failed to migrate user", ErrorCode.ServerError

    await update_searchdb(new_user)

    return True, UserGQL.from_db(new_user), None


async def mutate_reset_password(
    user_id: UUID,
    old_password: str,
    new_password: str,
) -> ResultOrT[UserGQL]:
    user = await ShowtimesUser.find_one(ShowtimesUser.user_id == user_id)
    if not user:
        return False, "User with associated email not found", ErrorCode.UserNotFound
    new_pass_hash = await encrypt_password(new_password)
    if user.password is None:
        return False, "User has no password set, please do password reset first", ErrorCode.UserMigrate
    if old_password == new_password:
        return False, "New password cannot be the same as old password", ErrorCode.UserRepeatOld

    if len(new_password) < 8:
        return False, "New password must be at least 8 characters long", ErrorCode.UserRequirementPass

    is_verify, _ = await verify_password(old_password, user.password)
    if not is_verify:
        return False, "Old password is not correct", ErrorCode.UserInvalidOldPass

    user.password = new_pass_hash
    await user.save()  # type: ignore
    return True, UserGQL.from_db(user), None


async def mutate_user_bind_integrations(
    username: str,
    password: str,
    integrations: list[IntegrationInputGQL],
) -> ResultOrT[ShowtimesUser]:
    logger.info(f"Logging in as {username}")
    user = await ShowtimesUser.find_one(ShowtimesUser.username == username)
    if not user:
        logger.warning(f"User {username} not found")
        return False, "User with associated username not found", ErrorCode.UserNotFound
    user = cast(ShowtimesUser, user)
    if user.password is None:
        logger.warning(f"User {username} has no password set")
        if user.discord_meta is not None:
            logger.warning(f"User {username} has discord meta, returning it")
            return False, "Please use Discord to login, or do password reset first", ErrorCode.UserDiscordMigrate
        return False, "User has no password set, please do password reset first", ErrorCode.UserMigrate

    is_verify, new_password = await verify_password(password, user.password)
    if not is_verify:
        logger.warning(f"User {username} password is not correct")
        return False, "Password is not correct", ErrorCode.UserInvalidPass
    if new_password is not None and user is not None:
        user.password = new_password

    add_integrations: list[IntegrationInputGQL] = []
    remove_integrations: list[IntegrationInputGQL] = []
    modify_integrations: list[IntegrationInputGQL] = []
    for idx, integration in enumerate(integrations):
        if not isinstance(integration, IntegrationInputGQL):
            raise TypeError(f"Integration[{idx}] must be an IntegrationInputGQL")

        if integration.action == IntegrationInputActionGQL.ADD:
            add_integrations.append(integration)
        elif integration.action == IntegrationInputActionGQL.DELETE:
            remove_integrations.append(integration)
        elif integration.action == IntegrationInputActionGQL.UPSERT:
            modify_integrations.append(integration)

    for integration in remove_integrations:
        _found_idx: int | None = None
        for int_integ in user.integrations:
            if int_integ.id == integration.id and int_integ.type == integration.type:
                _found_idx = user.integrations.index(int_integ)
                break

        if _found_idx is not None:
            user.integrations.pop(_found_idx)

    for integration in add_integrations:
        user.integrations.append(IntegrationId(id=integration.id, type=integration.type))

    for integration in modify_integrations:
        found_any = False
        for idx, proj_integration in enumerate(user.integrations):
            if proj_integration.type == integration.type and proj_integration.id != integration.id:
                user.integrations[idx].id = integration.id
                found_any = True
                break
        if not found_any:
            user.integrations.append(IntegrationId(id=integration.id, type=integration.type))

    await user.save()  # type: ignore
    logger.info(f"Provided integrations has been applied to user {username}")
    return True, user, None
