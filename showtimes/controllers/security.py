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
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from argon2.profiles import RFC_9106_LOW_MEMORY

__all__ = (
    "get_argon2",
    "encrypt_password",
    "verify_password",
)


# Cache the PasswordHasher object, make it consistent between version and use
# the low memory RFC profile.
_ARGON2_HASHER = PasswordHasher(
    time_cost=RFC_9106_LOW_MEMORY.time_cost,
    memory_cost=RFC_9106_LOW_MEMORY.memory_cost,
    parallelism=RFC_9106_LOW_MEMORY.parallelism,
    hash_len=RFC_9106_LOW_MEMORY.hash_len,
    salt_len=RFC_9106_LOW_MEMORY.salt_len,
    encoding="utf-8",
    type=RFC_9106_LOW_MEMORY.type,
)


def get_argon2() -> PasswordHasher:
    return _ARGON2_HASHER


async def encrypt_password(password: str | bytes, *, loop: asyncio.AbstractEventLoop | None = None):
    loop = loop or asyncio.get_event_loop()
    if not isinstance(password, bytes):
        password = password.encode("utf-8")

    hashed = await loop.run_in_executor(None, get_argon2().hash, password)
    return hashed


async def verify_password(
    password: str,
    hashed_password: str,
    *,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[bool, Optional[str]]:
    """
    Verify the password with hashed argon2 password.
    Return a tuple of (is_verified, new_hashed_password)
    """

    loop = loop or asyncio.get_event_loop()

    try:
        is_correct = await loop.run_in_executor(None, get_argon2().verify, hashed_password, password)
    except VerifyMismatchError:
        is_correct = False
    if is_correct:
        need_rehash = await loop.run_in_executor(None, get_argon2().check_needs_rehash, hashed_password)
        if need_rehash:
            new_hashed = await encrypt_password(password, loop=loop)
            return True, new_hashed
        return True, None
    return False, None
