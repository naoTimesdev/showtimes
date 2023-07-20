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

import aiohttp

from showtimes.models.abstract import AttributeDict
from showtimes.tooling import get_env_config

from ..._metadata import __version__ as app_version

__all__ = (
    "discord_exchange_token",
    "discord_refresh_token",
    "discord_get_user_info",
    "discord_get_user_guilds",
)
env_conf = get_env_config()

RespT = TypeVar("RespT", bound=AttributeDict)
ResponseT = tuple[RespT | None, str]
ResponseListT = tuple[list[RespT] | None, str]
BASE_URL = "https://discord.com/api/v10"
DISCORD_ID = env_conf.get("DISCORD_CLIENT_ID")
DISCORD_SECRET = env_conf.get("DISCORD_CLIENT_SECRET")


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


async def discord_exchange_token(code: str, state_data: DiscordStateExchange) -> ResponseT[DiscordToken]:
    if DISCORD_ID is None or DISCORD_SECRET is None:
        return None, "Discord client is unavailable."

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

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/oauth2/token", data=params, headers=headers) as resp:
            resp.raise_for_status()

            resp_data = DiscordToken(await resp.json())
            return resp_data, "Successfully exchanged token."


async def discord_refresh_token(refresh_token: str) -> ResponseT[DiscordToken]:
    if DISCORD_ID is None or DISCORD_SECRET is None:
        return None, "Discord client is unavailable."

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

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/oauth2/token", data=params, headers=headers) as resp:
            resp.raise_for_status()

            resp_data = DiscordToken(await resp.json())
            return resp_data, "Successfully exchanged token."


async def discord_get_user_info(token: str) -> ResponseT[DiscordAPIUser]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/users/@me", headers=headers) as resp:
            resp.raise_for_status()

            resp_data = DiscordAPIUser(await resp.json())
            return resp_data, "Success"


async def discord_get_user_guilds(token: str) -> ResponseListT[DiscordAPIPartialGuild]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": f"Showtimes-API/{app_version} (+https://github.com/naoTimesdev/showtimes)",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{BASE_URL}/users/@me/guilds", headers=headers) as resp:
            resp.raise_for_status()

            resp_data = [DiscordAPIPartialGuild(guild) for guild in await resp.json()]
            return resp_data, "Success"
