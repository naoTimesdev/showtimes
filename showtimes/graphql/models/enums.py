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

from showtimes.models.database import ShowExternalType, ShowProjectType, ShowtimesTempUserType, UserType

__all__ = (
    "UserTypeGQL",
    "UserTempTypeGQL",
    "ProjectExternalTypeGQL",
    "ProjectTypeGQL",
    "SearchExternalTypeGQL",
    "SearchTitleTypeGQL",
    "SearchSourceTypeGQL",
    "IntegrationInputActionGQL",
    "ProjectInputAssigneeActionGQL",
    "ProjectPredictionModelGQL",
)

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
ProjectExternalTypeGQL = gql.enum(
    ShowExternalType,
    name="ProjectExternalType",
    description="The external project type or source type",
)
ProjectTypeGQL = gql.enum(
    ShowProjectType,
    name="ProjectType",
    description="The project type",
)


@gql.enum(name="SearchExternalType", description="The external search type")
class SearchExternalTypeGQL(Enum):
    SHOWS = "shows"
    MOVIE = "movie"
    BOOKS = "books"
    UNKNOWN = "unknown"


@gql.enum(name="SearchTitleType", description="Select title type to be shown in search results")
class SearchTitleTypeGQL(Enum):
    ENGLISH = "english"
    ROMANIZED = "romanized"
    NATIVE = "native"


@gql.enum(name="SearchSourceType", description="The source type of the search result")
class SearchSourceTypeGQL(Enum):
    ANILIST = "anilist"
    TMDB = "tmdb"
    DATABASE = "database"
    UNKNOWN = "unknown"


@gql.enum(name="IntegrationInputAction", description="The action to be taken for the integration")
class IntegrationInputActionGQL(Enum):
    ADD = "add"
    """Add the integration even if similar stuff exists"""
    DELETE = "delete"
    """Delete the integration if it exists"""
    UPSERT = "modify"
    """Modify the integration if it exists, otherwise add it"""


@gql.enum(name="ProjectInputAssigneeAction", description="The action to be taken for the assignments")
class ProjectInputAssigneeActionGQL(Enum):
    DELETE = "delete"
    """Delete the assignee if it exists, will also delete the assignee's status"""
    UPSERT = "modify"
    """Modify the assignee if it exists, otherwise add it (default)"""


@gql.enum(name="ProjectPredictionModel", description="The prediction model for the project")
class ProjectPredictionModelGQL(Enum):
    HISTORY = "history"
    """Use history data for the prediction"""
    SIMULATED = "simulated"
    """Use history data with extra simulated noise for the prediction"""
