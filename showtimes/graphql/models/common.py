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

from typing import Type

import strawberry as gql

from showtimes.graphql.models.enums import IntegrationInputActionGQL
from showtimes.models.database import ImageMetadata, IntegrationId

__all__ = (
    "IntegrationGQL",
    "IntegrationInputGQL",
    "ImageMetadataGQL",
)


@gql.type(name="Integration", description="The integration information")
class IntegrationGQL:
    id: str = gql.field(description="The integration ID or value")
    """The integration ID"""
    type: str = gql.field(description="The integration type (in full capital)")
    """The integration type"""

    @classmethod
    def from_db(cls: Type[IntegrationGQL], integration: IntegrationId):
        return cls(
            id=integration.id,
            type=integration.type,
        )


@gql.input(name="IntegrationInput", description="The integration information")
class IntegrationInputGQL:
    id: str = gql.field(description="The integration ID or value")
    """The integration ID"""
    type: str = gql.field(description="The integration type (in full capital)")
    """The integration type"""
    action: IntegrationInputActionGQL = gql.field(description="The integration action")
    """The integration action"""


@gql.type(name="ImageMetadata", description="An image for an entity")
class ImageMetadataGQL:
    path: str = gql.field(description="The path to the image")
    type: str = gql.field(description="The type of the avatar (user, group, shows, etc)")

    @classmethod
    def from_db(cls, avatar: ImageMetadata):
        return cls(
            path=avatar.as_url(),
            type=avatar.type,
        )
