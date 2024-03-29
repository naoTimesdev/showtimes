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

from typing import Generic, Optional, TypeVar

import strawberry as gql

from .users import UserGQL

__all__ = (
    "Result",
    "NodeResult",
    "UserResult",
    "ErrorCode",
)

NodeT = TypeVar("NodeT")


@gql.type(description="Simple result of mutation or an error")
class Result:
    success: bool = gql.field(description="Success status")
    message: Optional[str] = gql.field(description="Extra message if any, might be available if success is False")
    code: Optional[str] = gql.field(description="Extra code if any, might be available if success is False")


@gql.type(description="Simple result wrapper for a list")
class NodeResult(Generic[NodeT]):
    nodes: list[NodeT] = gql.field(description="List of nodes")


class ErrorCode:
    # User related
    UserNotFound = "USER_NOT_FOUND"
    UserAlreadyExist = "USER_ALREADY_EXIST"
    UserMigrate = "USER_NEED_MIGRATE"
    UserDiscordMigrate = "USER_LEGACY_DISCORD_AUTH"
    UserApprovalIncorrect = "USER_APPROVAL_INCORRECT"
    UserInvalidPass = "USER_INVALID_PASSWORD"
    UserMigrateNotInitiated = "USER_MIGRATE_NOT_INITIATED"
    UserRequirementPass = "USER_REQUIREMENT_PASSWORD"
    UserRequirementUsernameShort = "USER_REQUIREMENT_USERNAME_SHORT"
    UserRequirementUsernameLong = "USER_REQUIREMENT_USERNAME_LONG"
    UserRequirementUsernameInvalid = "USER_REQUIREMENT_USERNAME_INVALID"
    UserInvalidOldPass = "USER_INVALID_OLD_PASSWORD"
    UserRepeatOld = "USER_REPEAT_OLD_PASSWORD"
    SessionExist = "SESSION_EXIST"
    SessionUnknown = "SESSION_UNKNOWN"
    SessionNotMaster = "SESSION_NOT_MASTER"
    SessionNotAllowed = "SESSION_NOT_ALLOWED"
    AnilistAPIError = "ANILIST_API_ERROR"
    AnilistAPIUnavailable = "ANILIST_API_UNAVAILABLE"
    TMDbAPIUnavailable = "TMDB_API_UNAVAILABLE"
    TMDbAPIError = "TMDB_API_ERROR"
    ServerUnselect = "SERVER_UNSELECT"
    ServerNotFound = "SERVER_NOT_FOUND"
    ServerNotAllowed = "SERVER_NOT_ALLOWED"
    ServerOwnerNotAllowed = "SERVER_ADMIN_NOT_ALLOWED"
    ServerError = "SERVER_ERROR"
    ProjectNotFound = "PROJECT_NOT_FOUND"
    ImageUploadFailed = "IMAGE_UPLOAD_FAILED"

    # Add
    ServerAddMissingName = "SERVER_ADD_MISSING_NAME"
    ProjectAddMissingExternal = "PROJECT_ADD_MISSING_EXTERNAL"
    ProjectAddUnsupportedExternal = "PROJECT_ADD_UNSUPPORTED_EXTERNAL"
    ProjectAddStartTimeUnknown = "PROJECT_ADD_START_TIME_UNKNOWN"

    # Update
    ProjectUpdateNoEpisode = "PROJECT_UPDATE_NO_EPISODE"

    Success = "SUCCESS"
    NotImplemented = "NOT_IMPLEMENTED"


UserResult = gql.union(
    "UserResult", (Result, UserGQL), description="Either `User` if success or `Result` if failure detected"
)
