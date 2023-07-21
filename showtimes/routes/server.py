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

from dataclasses import dataclass

from fastapi import APIRouter
from fastapi.datastructures import Default

from showtimes.controllers.claim import get_claim_status
from showtimes.controllers.security import encrypt_password
from showtimes.models.database import ShowtimesUser, UserType

from ..extensions.fastapi.responses import ORJSONXResponse, ResponseType

__all__ = ("router",)
router = APIRouter(
    prefix="/server",
    default_response_class=Default(ORJSONXResponse),
    tags=["Servers"],
)


@dataclass
class ServerClaimRequest:
    username: str
    password: str


@router.post("/claim")
async def server_claim_post(claim_request: ServerClaimRequest):
    claim_latch = get_claim_status()
    if claim_latch.claimed:
        return ResponseType(error="Server already claimed", code=400).to_orjson(400)

    # Claim server
    user_admin = ShowtimesUser(
        username=claim_request.username,
        password=await encrypt_password(claim_request.password),
        privilege=UserType.ADMIN,
    )

    await user_admin.save()  # type: ignore
    claim_latch.claimed = True

    return ResponseType(error="Server claimed").to_orjson()


@router.get("/claim")
def server_claim_get():
    claim_latch = get_claim_status()
    return ResponseType(data=claim_latch.claimed).to_orjson()
