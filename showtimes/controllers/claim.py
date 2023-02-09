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

from showtimes.models.database import ShowtimesUser, UserType

__all__ = (
    "get_claim_status",
    "ClaimStatusLatch",
)


class ClaimStatusLatch:
    def __init__(self) -> None:
        self.__claimed = False

    @property
    def claimed(self):
        return self.__claimed

    @claimed.setter
    def claimed(self, value: bool):
        self.__claimed = bool(value)

    def __bool__(self):
        return self.__claimed

    async def set_from_db(self):
        total = await ShowtimesUser.find_one(ShowtimesUser.privilege == UserType.ADMIN).count()
        self.__claimed = total > 0


_ClaimLatch = ClaimStatusLatch()


def get_claim_status():
    return _ClaimLatch
