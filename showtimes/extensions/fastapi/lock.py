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

from showtimes.tooling import get_logger

__all__ = ("get_ready_status",)
logger = get_logger("Showtimes.Extensions.FastAPI.Lock")


class _SimpleFastAPILatch:
    def __init__(self) -> None:
        logger.debug("Initializing latch...")
        self._ready = False

    def ready(self) -> None:
        logger.debug("Latch triggered!")
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

    def unready(self) -> None:
        logger.debug("Latch untriggered!")
        self._ready = False


_APP_READY = _SimpleFastAPILatch()


def get_ready_status():
    global _APP_READY

    return _APP_READY
