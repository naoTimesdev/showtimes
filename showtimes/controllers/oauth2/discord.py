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

from typing import Literal, TypedDict, TypeVar

import httpx
import orjson

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.models.abstract import AttributeDict
from showtimes.tooling import get_env_config, get_logger

from ..._metadata import __version__ as app_version

__all__ = (
    "DiscordOAuth2API",
    "init_discord_oauth2_api",
    "get_discord_oauth2_api",
)
env_conf = get_env_config()

RespT = TypeVar("RespT", bound=AttributeDict)
ResponseT = tuple[RespT | None, str]
ResponseListT = tuple[list[RespT] | None, str]
BASE_URL = "https://discord.com/api/v10"
DISCORD_ID = env_conf.get("DISCORD_CLIENT_ID")
DISCORD_SECRET = env_conf.get("DISCORD_CLIENT_SECRET")
logger = get_logger("Showtimes.Controlers.OAuth2.Discord")


class DiscordToken(AttributeDict):
    access_token: str
    refresh_token: str
    expires_in: int
    scope: str
    token_type: str


class DiscordState(TypedDict):
    client_id: str
    redirect_uri: str
    response_type: Literal["code"]
    prompt: Literal["consent"]
    scope: str
    state: str


class DiscordStateExchange(DiscordState):
    final_redirect: str


class DiscordAPIUser(AttributeDict):
    id: int
    username: str
    discriminator: int
    avatar: int
    bot: bool
    mfa_enabled: bool
    locale: int
    verified: bool
    email: int
    flags: int
    premium_type: int
    public_flags: int


class DiscordAPIPartialGuild(AttributeDict):
    id: str
    name: str
    icon: str
    owner: bool
    permissions: str
    features: list[str]


class DiscordOAuth2API:
    def __init__(self, *, session: httpx.AsyncClient | None = None) -> None:
        if DISCORD_ID is None or DISCORD_SECRET is None:
            raise RuntimeError("Discord client is unavailable.")
        self._client = session or httpx.AsyncClient()

    async def exchange_token(self, code: str, state_data: DiscordStateExchange) -> ResponseT[DiscordToken]:
        params = {
            "client_id": DISCORD_ID,
            "client_secret": DISCORD_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": state_data["redirect_uri"],
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
        }

        logger.debug(f"Exchanging token for {params}")
        resp = await self._client.post(f"{BASE_URL}/oauth2/token", data=params, headers=headers)
        resp.raise_for_status()

        resp_data = DiscordToken(orjson.loads(await resp.aread()))
        return resp_data, "Successfully exchanged token."

    async def refresh_token(self, refresh_token: str) -> ResponseT[DiscordToken]:
        params = {
            "client_id": DISCORD_ID,
            "client_secret": DISCORD_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
        }

        logger.debug(f"Refreshing token for {params}")
        resp = await self._client.post(f"{BASE_URL}/oauth2/token", data=params, headers=headers)
        resp.raise_for_status()

        resp_data = DiscordToken(orjson.loads(await resp.aread()))
        return resp_data, "Successfully refreshed token."

    async def get_user(self, token: str) -> ResponseT[DiscordAPIUser]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
        }

        resp = await self._client.post(f"{BASE_URL}/users/@me", headers=headers)
        resp.raise_for_status()

        resp_data = DiscordAPIUser(orjson.loads(await resp.aread()))
        return resp_data, "Success"

    async def get_guilds(self, token: str) -> ResponseListT[DiscordAPIPartialGuild]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
        }

        resp = await self._client.post(f"{BASE_URL}/users/@me/guilds", headers=headers)
        resp.raise_for_status()

        resp_data = [DiscordAPIPartialGuild(guild) for guild in orjson.loads(await resp.aread())]
        return resp_data, "Success"


_DISCORD_CLIENT = DiscordOAuth2API()


async def init_discord_oauth2_api() -> DiscordOAuth2API:
    global _DISCORD_CLIENT

    if _DISCORD_CLIENT is None:
        _DISCORD_CLIENT = DiscordOAuth2API()

    return _DISCORD_CLIENT


def get_discord_oauth2_api() -> DiscordOAuth2API:
    global _DISCORD_CLIENT

    if _DISCORD_CLIENT is None:
        raise ShowtimesControllerUninitializedError("Discord OAuth2 API")

    return _DISCORD_CLIENT
