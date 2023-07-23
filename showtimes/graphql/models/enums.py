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

from enum import Enum

import strawberry as gql

from showtimes.models.database import ShowtimesTempUserType, UserType

__all__ = ("UserTypeGQL", "UserTempTypeGQL", "SearchExternalTypeGQL")

UserTypeGQL = gql.enum(
    UserType,
    name="UserType",
    description="The user type",
)
UserTempTypeGQL = gql.enum(
    ShowtimesTempUserType,
    name="UserTempType",
    description="The temporary user type",
)


@gql.enum(name="SearchExternalType", description="The external search type")
class SearchExternalTypeGQL(Enum):
    SHOWS = "shows"
    BOOKS = "books"
    UNKNOWN = "unknown"


@gql.enum(name="SearchTitleType", description="Select title type to be shown in search results")
class SearchTitleTypeGQL(Enum):
    ENGLISH = "english"
    ROMANIZED = "romanized"
    NATIVE = "native"
