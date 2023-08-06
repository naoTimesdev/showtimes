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

from typing import Annotated, cast
from urllib.parse import quote, unquote

import httpx
import pendulum
from beanie.operators import Eq as OpEq
from beanie.operators import Or as OpOr
from fastapi import APIRouter, Depends, Request
from fastapi.datastructures import Default
from fastapi.responses import RedirectResponse

from showtimes.controllers.oauth2.discord import DiscordStateExchange, get_discord_oauth2_api
from showtimes.controllers.redisdb import get_redis
from showtimes.controllers.sessions.handler import get_session_handler
from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.extensions.fastapi.errors import ShowtimesException
from showtimes.graphql.mutations.users import mutate_login_user
from showtimes.models.database import DefaultIntegrationType, ShowtimesUser, ShowtimesUserDiscord, UserType
from showtimes.models.session import UserSession
from showtimes.tooling import get_env_config
from showtimes.utils import generate_custom_code

from ..extensions.fastapi.responses import ORJSONXResponse, ResponseType

__all__ = ("router",)
router = APIRouter(
    prefix="/oauth2",
    default_response_class=Default(ORJSONXResponse),
    tags=["OAuth2"],
)
env_conf = get_env_config()

DISCORD_ID = env_conf.get("DISCORD_CLIENT_ID")
DISCORD_SECRET = env_conf.get("DISCORD_CLIENT_SECRET")


def verify_discord_client():
    if DISCORD_ID is None or DISCORD_SECRET is None:
        raise ShowtimesException(500, "Discord client is unavailable.")


async def protected(request: Request):
    session = get_session_handler()
    response = await session(request)
    return response


@router.post("/password", response_model=ResponseType, description="Login using username and password.")
async def oauth2_password_login(username: str, password: str):
    session_handler = get_session_handler()
    _, show_user, _ = await mutate_login_user(username, password)
    if isinstance(show_user, ShowtimesUser):
        response_data = ResponseType(error="Successfully logged in.", code=200).to_orjson(200)
        await session_handler.set_session(UserSession.from_db(show_user), response_data)
        return response_data

    return ResponseType(error=show_user, code=400).to_orjson(400)


@router.post("/logout", response_model=ResponseType, description="Logout session.")
async def oauth2_password_logout(user: Annotated[UserSession, Depends(protected)]):
    session_handler = get_session_handler()
    response_data = ResponseType(error="Successfully logged out.", code=200).to_orjson(200)
    await session_handler.remove_session(user, response_data)

    return response_data


discord_router = APIRouter(
    prefix="/discord",
    default_response_class=Default(ORJSONXResponse),
    dependencies=[Depends(verify_discord_client)],
)


@discord_router.get("/authorize", response_class=RedirectResponse, status_code=302)
async def oauth2_discord_authorize(base_url: str, redirect_url: str):
    redis = get_redis()
    redirect_url = unquote(redirect_url)
    base_url = unquote(base_url)
    if base_url.endswith("/"):
        base_url = base_url[:-1]

    state_jacking = generate_custom_code(16, True)
    scopes = ["identify", "email", "guilds", "guilds.members.read"]

    params = {
        "client_id": cast(str, DISCORD_ID),
        "redirect_uri": f"{base_url}/oauth2/discord/exchange",
        "response_type": "code",
        "prompt": "consent",
        "scope": " ".join(scopes),
        "state": state_jacking,
    }

    success = await redis.set(
        f"showtimes:oauth2:discord:state:{state_jacking}",
        {
            **params,
            "final_redirect": redirect_url,
        },
    )
    if not success:
        raise ShowtimesException(500, "Failed to create state parameter.")

    encoded_params = "&".join([f"{k}={quote(v)}" for k, v in params.items()])
    return RedirectResponse(f"https://discord.com/oauth2/authorize?{encoded_params}", 302)


@discord_router.get("/exchange", response_class=RedirectResponse, status_code=302)
async def oauth2_discord_token_exchange(code: str, state: str):
    redis = get_redis()

    state = unquote(state)
    state_data = cast(DiscordStateExchange | None, await redis.get(f"showtimes:oauth2:discord:state:{state}"))
    if state_data is None:
        raise ShowtimesException(400, "Unknown state parameter.")

    if state_data["state"] != state:
        raise ShowtimesException(400, "Invalid state parameter.")

    try:
        oauth_api = get_discord_oauth2_api()
    except ShowtimesControllerUninitializedError as e:
        raise ShowtimesException(500, "Discord OAuth2 controller is unavailable.") from e

    try:
        exchange_tok, error = await oauth_api.exchange_token(code, state_data)
    except httpx.HTTPStatusError as e:
        raise ShowtimesException(500, f"Failed to authorize Discord code: {e}") from e

    if exchange_tok is None:
        raise ShowtimesException(500, f"Failed to authorize Discord code: {error}")

    try:
        user_info, error = await oauth_api.get_user(exchange_tok.access_token)
    except httpx.HTTPStatusError as e:
        raise ShowtimesException(500, f"Failed to get user info: {e}") from e

    if user_info is None:
        raise ShowtimesException(500, f"Failed to get user info: {error}")

    user_db = await ShowtimesUser.find_one(
        OpOr(
            OpEq("discord_meta.id", str(user_info.id)),
            {
                "integrations.id": str(user_info.id),
                "integrations.type": DefaultIntegrationType.DiscordUser,
            },
        )
    )
    expires_at = pendulum.now(tz="UTC").add(seconds=exchange_tok.expires_in)

    if user_db is None:
        user_db = ShowtimesUser(
            username=str(user_info.id),
            password=None,
            name=user_info.username,
            privilege=UserType.USER,
            discord_meta=ShowtimesUserDiscord(
                id=str(user_info.id),
                name=user_info.username,
                access_token=exchange_tok.access_token,
                refresh_token=exchange_tok.refresh_token,
                expires_at=expires_at.timestamp(),
            ),
        )

    await user_db.save()  # type: ignore

    session = get_session_handler()
    response_object = RedirectResponse(state_data["final_redirect"], status_code=302)
    await session.set_session(UserSession.from_db(user_db), response_object)
    return response_object


router.include_router(discord_router)
