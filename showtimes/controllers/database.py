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

import logging
import time
from typing import TYPE_CHECKING, Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

if TYPE_CHECKING:
    from motor.core import AgnosticClient, AgnosticDatabase

from showtimes.models.database import (
    RoleActor,
    ShowExternalAnilist,
    ShowExternalTMDB,
    ShowProject,
    ShowtimesServer,
    ShowtimesUser,
)

__all__ = ("ShowtimesDatabase",)


class ShowtimesDatabase:
    def __init__(
        self,
        ip_hostname_or_url: str,
        port: int = 27017,
        dbname: str = "showtimesdb",
        auth_string: Optional[str] = None,
        auth_source: str = "admin",
        tls: bool = False,
    ):
        self.logger = logging.getLogger("Showtimes.Controllers.Database")
        self.__ip_hostname_or_url = ip_hostname_or_url
        self._port = port
        self._dbname = dbname
        self._auth_string = auth_string
        self._auth_source = auth_source
        self._tls = tls

        self._url = self.__ip_hostname_or_url if self.__ip_hostname_or_url.startswith("mongodb") else ""
        self._ip_hostname = ""
        if self._url == "":
            self._ip_hostname = self.__ip_hostname_or_url
            self._generate_url()

        self._client: AgnosticClient = AsyncIOMotorClient(self._url)
        self._db: AgnosticDatabase = self._client[self._dbname]

    @property
    def db(self):
        return self._db

    def _generate_url(self):
        self._url = "mongodb"
        if self._tls:
            self._url += "+srv"
        self._url += "://"
        if self._auth_string:
            self._url += self._auth_string + "@"
        self._url += f"{self._ip_hostname}"
        if not self._tls:
            self._url += f":{self._port}"
        self._url += "/"
        self._url += f"?authSource={self._auth_source}&readPreference=primary&directConnection=true"
        if self._tls:
            self._url += "&retryWrites=true&w=majority"

    async def validate_connection(self):
        return await self._db.command({"ping": 1})  # type: ignore

    async def ping_server(self):
        t1_ping = time.perf_counter()
        self.logger.info("pinging server...")
        try:
            res = await self.validate_connection()
            t2_ping = time.perf_counter()
            if "ok" in res and int(res["ok"]) == 1:
                return True, (t2_ping - t1_ping) * 1000
            return False, 99999
        except (ValueError, PyMongoError):
            return False, 99999

    async def connect(self):
        await init_beanie(
            database=self._db,
            document_models=[
                RoleActor,
                ShowExternalAnilist,
                ShowExternalTMDB,
                ShowProject,
                ShowtimesServer,
                ShowtimesUser,
            ],  # type: ignore (complained badly)
        )
