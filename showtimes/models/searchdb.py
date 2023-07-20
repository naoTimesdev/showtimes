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

from dataclasses import Field, dataclass
from typing import Any, ClassVar, Protocol, Type, TypeVar

import orjson

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

        if config is None:
            raise TypeError(f"Class `{cls.__name__}` must have a `Config` class!")

        config_name = getattr(config, "index", None)
        if not isinstance(config_name, str):
            raise TypeError(f"Class `{cls.__name__}` must have a `index` attribute in `Config` class!")

        if len(config_name) < 1:
            raise ValueError(f"Class `{cls.__name__}` must have a `index` attribute in `Config` class!")

    class Config:
        index: str


@dataclass
class ServerSearch(SchemaAble):
    id: str
    name: str
    projects: list[str]

    class Config:
        index = "servers"


@dataclass
class ProjectSearch(SchemaAble):
    id: str
    title: str
    poster_url: str
    created_at: int
    updated_at: int
    server_id: str

    class Config:
        index = "projects"


@dataclass
class UserImageMetadata:
    key: str
    format: str


@dataclass
class UserSearch(SchemaAble):
    id: str
    username: str
    name: str | None = None
    avatar_url: UserImageMetadata | None = None

    class Config:
        index = "users"
