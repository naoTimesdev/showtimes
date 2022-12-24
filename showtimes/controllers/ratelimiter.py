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

import asyncio
import logging
from datetime import datetime

__all__ = ("NetworkRateLimiter",)


class NetworkRateLimiter:
    """
    An async context manager that limits the number of requests per second.

    The provided value will be default request per second that the API provides.
    Make sure that the user can adjust the remaining from the API headers.
    Like:
    - X-RateLimit-Limit: 100
    - X-RateLimit-Remaining: 99
    - X-RateLimit-Reset: 1620000000
    """

    def __init__(self, request_limit: int, rate_in_second: int) -> None:
        self.__limit = request_limit
        self.__remaining = request_limit
        self.__rate = rate_in_second
        self.__next_reset = datetime.utcnow().timestamp() + rate_in_second
        self.__logger = logging.getLogger("Controllers.RateLimiter")

    @property
    def next_reset(self) -> float:
        return self.__next_reset

    @property
    def remaining(self) -> int:
        return self.__remaining

    @property
    def rate(self) -> int:
        return self.__rate

    @property
    def limit(self) -> int:
        return self.__limit

    @next_reset.setter
    def next_reset(self, value: float | int | str) -> None:
        if isinstance(value, (float, int)):
            self.__next_reset = value
        elif isinstance(value, str):
            val: int | float | None = None
            try:
                val = float(value)
            except ValueError:
                try:
                    val = int(value)
                except ValueError:
                    pass
            if val is not None:
                self.__next_reset = val

    @remaining.setter
    def remaining(self, value: int | str) -> None:
        if isinstance(value, int):
            self.__remaining = value
        elif isinstance(value, str):
            val: int | None = None
            try:
                val = int(value)
            except ValueError:
                pass
            if val is not None:
                self.__remaining = val

    @rate.setter
    def rate(self, value: int | str) -> None:
        if isinstance(value, int):
            self.__rate = value
        elif isinstance(value, str):
            val: int | None = None
            try:
                val = int(value)
            except ValueError:
                pass
            if val is not None:
                self.__rate = val

    @limit.setter
    def limit(self, value: int | str) -> None:
        if isinstance(value, int):
            self.__limit = value
        elif isinstance(value, str):
            val: int | None = None
            try:
                val = int(value)
            except ValueError:
                pass
            if val is not None:
                self.__limit = val

    async def wait(self):
        diff = self.__next_reset - datetime.utcnow().timestamp()
        self.__next_reset = datetime.utcnow().timestamp() + self.__rate
        if diff > 0:
            self.__logger.debug("Rate limited, stalling for %.2f seconds", diff)
            await asyncio.sleep(diff)
            self.__remaining = self.__limit

    async def drip(self):
        # Drip/allow a request
        if self.__remaining <= 0:
            await self.wait()
        self.__remaining -= 1

    # Iter mode
    async def __anext__(self):
        await self.drip()
        return self

    def __aiter__(self):
        return self
