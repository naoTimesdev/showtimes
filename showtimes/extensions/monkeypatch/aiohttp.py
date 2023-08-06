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

# Quick monkeypatch to aiohttp that will replace TCPConnector with certifi context.
import ssl

import aiohttp
import certifi

from showtimes.tooling import get_logger

__all__ = ("monkeypatch_aiohttp_tcp_ssl_certifi",)
logger = get_logger("Showtimes.Extensions.Monkeypatch.aiohttp")


def monkeypatch_aiohttp_tcp_ssl_certifi():
    def aiohttp_init(self: aiohttp.ClientSession, *args, **kwargs):
        super(aiohttp.ClientSession, self).__init__(*args, **kwargs)
        old_loop = self._connector._loop  # type: ignore
        self._connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()), loop=old_loop)

    logger.info("Monkeypatching aiohttp to use certifi context.")
    aiohttp.ClientSession.__init__ = aiohttp_init
    logger.info("Monkeypatched aiohttp to use certifi context.")
