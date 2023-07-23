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

from typing import Optional

import strawberry as gql

from .users import UserGQL

__all__ = (
    "Result",
    "UserResult",
    "ErrorCode",
)


@gql.type(description="Simple result of mutation")
class Result:
    success: bool = gql.field(description="Success status")
    message: Optional[str] = gql.field(description="Extra message if any, might be available if success is False")
    code: Optional[str] = gql.field(description="Extra code if any, might be available if success is False")


class ErrorCode:
    # User related
    UserNotFound = "USER_NOT_FOUND"
    UserAlreadyExist = "USER_ALREADY_EXIST"
    UserMigrate = "USER_NEED_MIGRATE"
    UserApprovalIncorrect = "USER_APPROVAL_INCORRECT"
    UserInvalidPass = "USER_INVALID_PASSWORD"
    UserInvalidOldPass = "USER_INVALID_OLD_PASSWORD"
    UserRepeatOld = "USER_REPEAT_OLD_PASSWORD"
    SessionExist = "SESSION_EXIST"
    SessionUnknown = "SESSION_UNKNOWN"
    SessionNotMaster = "SESSION_NOT_MASTER"
    AnilistAPIError = "ANILIST_API_ERROR"
    AnilistAPIUnavailable = "ANILIST_API_UNAVAILABLE"


UserResult = gql.union(
    "UserResult", (Result, UserGQL), description="Either `User` if success or `Result` if failure detected"
)
