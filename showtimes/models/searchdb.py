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

from dataclasses import Field, dataclass, field
from inspect import isclass
from typing import Any, ClassVar, Protocol, Type, TypeVar

import orjson

from showtimes.models.database import ShowProject, ShowtimesServer, ShowtimesUser, ShowtimesUserGroup

__all__ = (
    "SchemaAble",
    "ServerSearch",
    "ProjectSearch",
    "UserSearch",
)


class _SimpleDataclass(Protocol):
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]


_SchemaSupported = TypeVar("_SchemaSupported", bound=_SimpleDataclass)


class SchemaAble:
    """
    A protocol that allows a :class:`dataclass` object to be
    transformed into a :class:`tantivy.Schema` object.

    Usages
    -------
    ```py
    @dataclass
    class Person(SchemaAble):
        name: str
        age: int
    ```
    """

    def to_dict(self: Type[_SchemaSupported]) -> dict[str, Any]:
        """
        Transform a :class:`dataclass` object into a dictionary.

        Returns
        -------
        :class:`dict[str, Any]`
            The schema object.

        Raises
        ------
        :exc:`ValueError`
            If the class is not a valid :class:`dataclass` object.
        :exc:`TypeError`
            If the class has an unsupported type.
        """
        cls_name = self.__class__.__name__
        if not hasattr(self, "__dataclass_fields__"):
            raise ValueError(f"Unable to transform `{cls_name}` because it's not a `dataclass`-decorated class!")

        return orjson.loads(orjson.dumps(self))

    def to_json(self: Type[_SchemaSupported]) -> bytes:
        """
        Transform a :class:`dataclass` object into a JSON bytes.

        Returns
        -------
        :class:`bytes`
            The JSON bytes.

        Raises
        ------
        :exc:`ValueError`
            If the class is not a valid :class:`dataclass` object.
        :exc:`TypeError`
            If the class has an unsupported type.
        """
        cls_name = self.__class__.__name__
        if not hasattr(self, "__dataclass_fields__"):
            raise ValueError(f"Unable to transform `{cls_name}` because it's not a `dataclass`-decorated class!")

        return orjson.dumps(self)

    def __init_subclass__(cls) -> None:
        config = getattr(cls, "Config", None)

        # Check if config is a class
        if not isclass(config):
            raise TypeError(f"Class `{cls.__name__}` must have a `Config` inner class!")

        config_name = getattr(config, "index", None)
        if not isinstance(config_name, str):
            raise TypeError(f"Class `{cls.__name__}` must have a `index` attribute in `Config` inner class!")

        if len(config_name) < 1:
            raise ValueError(f"Class `{cls.__name__}` must have a `index` attribute in `Config` inner class!")

    class Config:
        index: str


@dataclass
class SearchIntegrationData:
    id: str
    type: str


@dataclass
class ServerSearch(SchemaAble):
    id: str
    name: str
    projects: list[str]  # MongoDB ObjectID
    integrations: list[SearchIntegrationData] = field(default_factory=list)

    class Config:
        index = "servers"

    @classmethod
    def from_db(cls: Type[ServerSearch], server: ShowtimesServer):
        project_ids = [str(project.ref.id) for project in server.projects]
        integrations = [SearchIntegrationData(integration.id, integration.type) for integration in server.integrations]
        return cls(
            id=str(server.server_id),
            name=server.name,
            projects=project_ids,
            integrations=integrations,
        )


@dataclass
class ProjectSearch(SchemaAble):
    id: str  # show_id
    title: str
    poster_url: str | None
    created_at: int
    updated_at: int
    server_id: str
    integrations: list[SearchIntegrationData] = field(default_factory=list)

    class Config:
        index = "projects"

    @classmethod
    def from_db(cls: Type[ProjectSearch], project: ShowProject):
        integrations = [SearchIntegrationData(integration.id, integration.type) for integration in project.integrations]
        return cls(
            id=str(project.show_id),
            title=project.title,
            poster_url=project.poster.image.as_url(),
            created_at=int(project.created_at.timestamp()),
            updated_at=int(project.updated_at.timestamp()),
            server_id=str(project.server_id),
            integrations=integrations,
        )


@dataclass
class UserSearch(SchemaAble):
    id: str
    username: str
    object_id: str  # MongoDB ObjectID
    type: str  # temp/registered
    integrations: list[SearchIntegrationData] = field(default_factory=list)
    name: str | None = None
    avatar_url: str | None = None

    class Config:
        index = "users"

    @classmethod
    def from_db(cls: Type[UserSearch], user: ShowtimesUserGroup):
        integrations = [SearchIntegrationData(integration.id, integration.type) for integration in user.integrations]
        utype = "tempuser"
        avatar_url = None
        if isinstance(user, ShowtimesUser):
            utype = "user"
            if user.avatar is not None:
                avatar_url = user.avatar.as_url()
        return cls(
            id=str(user.user_id),
            name=getattr(user, "name", None),
            username=user.username,
            object_id=str(user.id),
            type=utype,
            integrations=integrations,
            avatar_url=avatar_url,
        )
