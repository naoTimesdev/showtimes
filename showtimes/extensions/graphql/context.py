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

from typing import Optional

from strawberry.fastapi import BaseContext

from showtimes.controllers.sessions import SessionHandler
from showtimes.models.session import UserSession

__all__ = ("SessionQLContext",)


class SessionQLContext(BaseContext):
    def __init__(self, session: SessionHandler, user: Optional[UserSession] = None):
        self.session: SessionHandler = session
        self.user: Optional[UserSession] = user
        self.session_latch: bool = False
