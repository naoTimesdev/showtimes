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

import random
from string import ascii_lowercase, ascii_uppercase, digits
from typing import Any, Optional, overload
from uuid import UUID, uuid4

__all__ = (
    "make_uuid",
    "traverse",
    "get_indexed",
    "complex_walk",
    "generate_custom_code",
    "to_boolean",
    "try_int",
)


@overload
def make_uuid(stringify: bool = False) -> UUID:
    ...


@overload
def make_uuid(stringify: bool = True) -> str:
    ...


def make_uuid(stringify: bool = False) -> UUID | str:
    """
    Generate a UUID4 string.

    Returns
    -------
    str
        The generated UUID4 string
    """
    u = uuid4()
    return str(u) if stringify else u


def traverse(data: dict | list, notations: str) -> Any:
    """
    Traverse a dictionary or list using a string notation.

    Parameters
    ----------
    data : dict | list
        The data to traverse
    notations : str
        The notation to use to traverse the data

    Returns
    -------
    Any
        The result of the traversal
    """
    for nots in notations.split("."):
        if nots.isdigit():
            nots = int(nots, 10)  # type: ignore
        data = data[nots]  # type: ignore
    return data


def get_indexed(data: list, n: int) -> Optional[Any]:
    """
    Get an item from a list using an index.

    Parameters
    ----------
    data : list
        The list of traverse
    n : int
        The index to use

    Returns
    -------
    Optional[Any]
        The result of the traversal
    """
    if not data:
        return None
    try:
        return data[n]
    except (ValueError, IndexError):
        return None


def complex_walk(dictionary: dict | list, paths: str):
    if not dictionary:
        return None
    expanded_paths = paths.split(".")
    skip_it = False
    for n, path in enumerate(expanded_paths):
        if skip_it:
            skip_it = False
            continue
        if path.isdigit():
            path = int(path)  # type: ignore
        if path == "*" and isinstance(dictionary, list):
            new_concat = []
            next_path = get_indexed(expanded_paths, n + 1)
            if next_path is None:
                return None
            skip_it = True
            for content in dictionary:
                try:
                    new_concat.append(content[next_path])
                except (TypeError, ValueError, IndexError, KeyError, AttributeError):
                    pass
            if len(new_concat) < 1:
                return new_concat
            dictionary = new_concat
            continue
        try:
            dictionary = dictionary[path]  # type: ignore
        except (TypeError, ValueError, IndexError, KeyError, AttributeError):
            return None
    return dictionary


def generate_custom_code(length: int = 8, include_numbers: bool = False, include_uppercase: bool = False) -> str:
    """
    Generate a custom string of numbers, characters and/or uppercase characters.
    And return it according to the provided length.

    Parameters
    ----------
    length : int, optional
        How long the generated code will be, by default 8
    include_numbers : bool, optional
        Include numbers in the result, by default False
    include_uppercase : bool, optional
        Include uppercase letter in result, by default False

    Returns
    -------
    str
        The generated code
    """
    letters_used = ascii_lowercase
    if include_numbers:
        letters_used += digits
    if include_uppercase:
        letters_used += ascii_uppercase
    generated = "".join([random.choice(letters_used) for _ in range(length)])  # noqa: S311
    return generated


def to_boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in ("yes", "true", "t", "y", "1")
    return bool(value)


def try_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
