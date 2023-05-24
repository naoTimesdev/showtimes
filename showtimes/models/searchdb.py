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
from datetime import datetime
from typing import Any, ClassVar, Protocol, Type, TypeVar

import tantivy

__all__ = (
    "SchemaAble",
    "ServerSearch",
    "ProjectSearch",
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

    def to_schema(self: Type[_SchemaSupported]) -> tantivy.Schema:
        """
        Transform a :class:`dataclass` object into a :class:`tantivy.Schema` object.

        Returns
        -------
        :class:`tantivy.Schema`
            The schema object.

        Raises
        ------
        :exc:`ValueError`
            If the class is not a valid :class:`dataclass` object.
        :exc:`TypeError`
            If the class has an unsupported type.
        """
        cls_name = self.__name__
        if not hasattr(self, "__dataclass_fields__"):
            raise ValueError(f"Unable to transform `{cls_name}` because it's not a `dataclass`-decorated class!")
        dt_fields = self.__dataclass_fields__  # type: ignore

        sbuilder = tantivy.SchemaBuilder()
        for name, field in dt_fields.items():
            ftype = field.type
            if ftype == str:
                sbuilder.add_text_field(name, stored=True, tokenizer_name="en_stem")
            elif ftype == int:
                sbuilder.add_unsigned_field(name, stored=True)
            elif ftype == datetime:
                sbuilder.add_date_field(name, stored=True)
            elif ftype == bytes:
                sbuilder.add_bytes_field(name)
            elif ftype in (dict, list):  # TODO: Fix this
                sbuilder.add_json_field(name, stored=True)
            else:
                raise TypeError(
                    f"Unable to transform `{cls_name}` because `{name}` has an unsupported type `{ftype.__name__}`!"
                )
        return sbuilder.build()


@dataclass
class ServerSearch(SchemaAble):
    id: str
    name: str
    projects: list[str]


@dataclass
class ProjectSearch(SchemaAble):
    id: str
    title: str
    poster_url: str
    created_at: int
    updated_at: int
    server_id: str


x = ProjectSearch("1", "2", "3", 4, 5, "6")
print(x.to_schema())
