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
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.datastructures import Default

from showtimes.controllers.claim import get_claim_status
from showtimes.controllers.searcher import get_searcher
from showtimes.controllers.security import encrypt_password
from showtimes.controllers.sessions.handler import get_session_handler
from showtimes.graphql.mutations.common import query_aggregate_project_ids
from showtimes.models.database import ShowProject, ShowtimesServer, ShowtimesUser, UserType
from showtimes.models.searchdb import ProjectSearch, ServerSearch, UserSearch
from showtimes.models.session import UserSession

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

    if not claim_request.username:
        return ResponseType(error="Username cannot be empty", code=400).to_orjson(400)

    if not claim_request.password:
        return ResponseType(error="Password cannot be empty", code=400).to_orjson(400)

    if len(claim_request.password) < 8:
        return ResponseType(error="Password must be at least 8 characters long", code=400).to_orjson(400)
    if len(claim_request.password) > 128:
        return ResponseType(error="Password must be at most 128 characters long", code=400).to_orjson(400)

    if len(claim_request.username) < 4:
        return ResponseType(error="Username must be at least 4 characters long", code=400).to_orjson(400)

    # Claim server
    user_admin = ShowtimesUser(
        username=claim_request.username,
        password=await encrypt_password(claim_request.password),
        privilege=UserType.ADMIN,
    )

    await user_admin.save()  # type: ignore
    claim_latch.claimed = True
    searcher = get_searcher()
    await searcher.update_document(UserSearch.from_db(user_admin))

    return ResponseType(error="Server claimed").to_orjson()


@router.get("/claim")
def server_claim_get():
    claim_latch = get_claim_status()
    return ResponseType(data=claim_latch.claimed).to_orjson()


async def protected(request: Request):
    session = get_session_handler()
    response = await session(request)
    return response


@router.post("/reindex/users", response_model=ResponseType, description="Reindex the users to the search database")
async def server_search_reindex_users(user: Annotated[UserSession, Depends(protected)]):
    if user.privilege != UserType.ADMIN:
        return ResponseType(error="You are not authorized to perform this action", code=403).to_orjson(403)
    searcher = get_searcher()

    prompted_data = []
    async for show_user in ShowtimesUser.find_all():
        prompted_data.append(UserSearch.from_db(show_user))
    await searcher.update_documents(prompted_data)
    await searcher.update_facet(
        UserSearch.Config.index,
        ["id", "username", "integrations.id", "integrations.type"],
    )
    return ResponseType(error="Users is being reindexed").to_orjson()


@router.post("/reindex/servers", response_model=ResponseType, description="Reindex the servers to the search database")
async def server_search_reindex_servers(user: Annotated[UserSession, Depends(protected)]):
    if user.privilege != UserType.ADMIN:
        return ResponseType(error="You are not authorized to perform this action", code=403).to_orjson(403)
    searcher = get_searcher()

    prompted_data = []
    async for show_user in ShowtimesServer.find_all():
        projected_project = await query_aggregate_project_ids([uproj.ref.id for uproj in show_user.projects])
        show_search = ServerSearch.from_db(show_user)
        show_search.projects = [str(project.show_id) for project in projected_project]
        prompted_data.append(show_search)
    await searcher.update_documents(prompted_data)
    await searcher.update_facet(ServerSearch.Config.index, ["id", "integrations.id", "integrations.type", "projects"])
    return ResponseType(error="Servers is being reindexed").to_orjson()


@router.post(
    "/reindex/projects", response_model=ResponseType, description="Reindex the projects to the search database"
)
async def server_search_reindex_projects(user: Annotated[UserSession, Depends(protected)]):
    if user.privilege != UserType.ADMIN:
        return ResponseType(error="You are not authorized to perform this action", code=403).to_orjson(403)
    searcher = get_searcher()

    prompted_data = []
    async for show_user in ShowProject.find_all():
        prompted_data.append(ProjectSearch.from_db(show_user))
    await searcher.update_documents(prompted_data)
    await searcher.update_facet(ProjectSearch.Config.index, ["id", "integrations.id", "integrations.type", "server_id"])
    return ResponseType(error="Servers is being reindexed").to_orjson()
