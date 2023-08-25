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

from typing import Literal, TypeAlias, TypeVar
from uuid import UUID

import strawberry as gql
from beanie.operators import In as OpIn
from bson import ObjectId

from showtimes.controllers.searcher import get_searcher
from showtimes.extensions.graphql.files import delete_image_upload, handle_image_upload
from showtimes.graphql.models.common import IntegrationInputGQL
from showtimes.graphql.models.enums import IntegrationInputActionGQL
from showtimes.graphql.models.fallback import ErrorCode, Result
from showtimes.graphql.models.servers import ServerInputGQL
from showtimes.graphql.mutations.common import (
    async_raise_for_invalid_integrations,
    common_mutate_project_delete,
    query_aggregate_project_ids,
)
from showtimes.models.database import (
    ImageMetadata,
    ShowProject,
    ShowtimesServer,
    ShowtimesUser,
    ShowtimesUserGroup,
    to_link,
)
from showtimes.models.integrations import IntegrationId
from showtimes.models.searchdb import ServerSearch
from showtimes.models.timeseries import TimeSeriesServerDelete
from showtimes.tooling import get_logger

__all__ = (
    "mutate_server_add",
    "mutate_server_update",
    "mutate_server_delete",
    "mutate_server_update_owners",
)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]
logger = get_logger("Showtimes.GraphQL.Mutations.Servers")


async def update_searchdb(server: ShowtimesServer) -> None:
    logger.debug(f"Updating Server Search Index for server {server.server_id}")
    searcher = get_searcher()
    servers = ServerSearch.from_db(server)
    project_ids = await query_aggregate_project_ids([project.ref.id for project in server.projects])
    servers.projects = [str(project.show_id) for project in project_ids]
    await searcher.update_document(servers)


async def delete_searchdb(server: ShowtimesServer) -> None:
    logger.debug(f"Deleting Server Search Index for server {server.server_id}")
    searcher = get_searcher()
    await searcher.delete_document(ServerSearch.Config.index, str(server.server_id))


async def mutate_server_update(
    id: UUID,
    input_data: ServerInputGQL,
    owner_id: str | None = None,
) -> ResultOrT[ShowtimesServer]:
    logger.info(f"Updating server {id}")
    server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == id)

    if not server_info:
        logger.warning(f"Server {id} not found")
        return False, "Server not found", ErrorCode.ServerNotFound

    owners = [owner.ref.id for owner in server_info.owners]
    if owner_id and ObjectId(owner_id) not in owners:
        logger.warning(f"Owner {owner_id} not found")
        return False, "You are not one of the owner of this server", ErrorCode.ServerNotAllowed

    save_changes = False
    if isinstance(input_data.name, str) and input_data.name.strip() != server_info.name:
        server_info.name = input_data.name.strip()
        save_changes = True
    if input_data.avatar is not None and input_data.avatar is not gql.UNSET:
        logger.debug(f"Updating avatar for server {id}")
        if server_info.avatar:
            logger.debug(f"Deleting old avatar for server {id}")
            await delete_image_upload(server_info.avatar)
        upload_result = await handle_image_upload(
            input_data.avatar,
            str(server_info.server_id),
            filename="avatar",
            type="servers",
        )

        server_info.avatar = ImageMetadata(
            type="servers",
            key=str(server_info.server_id),
            filename=upload_result.filename,
            parent=None,
        )
        save_changes = True
    if isinstance(input_data.integrations, list):
        await async_raise_for_invalid_integrations(input_data.integrations)
        add_integrations: list[IntegrationInputGQL] = []
        remove_integrations: list[IntegrationInputGQL] = []
        modify_integrations: list[IntegrationInputGQL] = []
        for idx, integration in enumerate(input_data.integrations):
            if not isinstance(integration, IntegrationInputGQL):
                raise TypeError(f"Integration[{idx}] must be an IntegrationInputGQL")

            if integration.action == IntegrationInputActionGQL.ADD:
                add_integrations.append(integration)
            elif integration.action == IntegrationInputActionGQL.DELETE:
                remove_integrations.append(integration)

        if add_integrations:
            save_changes = True

        for integration in remove_integrations:
            _found_idx: int | None = None
            for int_integ in server_info.integrations:
                if int_integ.id == integration.id and int_integ.type == integration.type:
                    _found_idx = server_info.integrations.index(int_integ)
                    break

            if _found_idx is not None:
                save_changes = True
                server_info.integrations.pop(_found_idx)

        for integration in add_integrations:
            server_info.integrations.append(IntegrationId(id=integration.id, type=integration.type))

        for integration in modify_integrations:
            found_any = False
            for idx, server_integration in enumerate(server_info.integrations):
                if server_integration.type == integration.type and server_integration.id != integration.id:
                    server_info.integrations[idx].id = integration.id
                    found_any = True
                    break
            if not found_any:
                server_info.integrations.append(IntegrationId(id=integration.id, type=integration.type))
            save_changes = True

    if save_changes:
        logger.info(f"Saving changes for server {id}")
        await server_info.save()  # type: ignore
        await update_searchdb(server_info)
    else:
        logger.warning(f"No changes to save for server {id}")
    return True, server_info, None


async def mutate_server_update_owners(
    id: UUID,
    input_data: list[UUID],
    owner_id: str | None = None,
) -> ResultOrT[ShowtimesServer]:
    logger.info(f"Updating server owner {id}")
    server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == id)

    if not server_info:
        logger.warning(f"Server {id} not found")
        return False, "Server not found", ErrorCode.ServerNotFound

    owners = [owner.ref.id for owner in server_info.owners]
    if owner_id and ObjectId(owner_id) not in owners:
        logger.warning(f"Owner {owner_id} not found")
        return False, "You are not one of the owner of this server", ErrorCode.ServerNotAllowed
    first_owner: UUID | None = None

    user_info = await ShowtimesUserGroup.find(OpIn(ShowtimesUser.user_id, input_data), with_children=True).to_list()

    logger.info(f"Fetching owners for server {id} | {owners}")
    fetch_owners = await ShowtimesUserGroup.find(OpIn(ShowtimesUser.id, owners), with_children=True).to_list()
    first_owner_db = fetch_owners[0]
    logger.info(f"First owner is {first_owner_db} | {input_data}")
    ids_to_owner_server = {owner.user_id: owner for owner in fetch_owners}
    ids_to_owner_other = {owner.user_id: owner for owner in user_info}
    ids_to_owner_merge = {**ids_to_owner_server, **ids_to_owner_other}
    logger.info(f"IDs to owner from input data {ids_to_owner_server} | {input_data}")
    for owner in input_data:
        if owner == first_owner_db.user_id:
            first_owner = owner
            break

    if first_owner is None:
        logger.warning("First owner is deleted, cannot remove the first owner")
        return False, "You cannot remove the first owner of the server", ErrorCode.ServerOwnerNotAllowed

    input_data.remove(first_owner)
    logger.info(f"Removed owner {first_owner} | {input_data}")

    reposition_owners = [first_owner_db]
    for owner in input_data:
        owner_db = ids_to_owner_merge.get(owner)
        if owner_db is None:
            continue
        reposition_owners.append(owner_db)

    server_info.owners = [to_link(owner) for owner in reposition_owners]
    logger.info(f"Saving changes for server {id} | {reposition_owners}")
    await server_info.save()  # type: ignore
    await update_searchdb(server_info)
    return True, server_info, None


async def mutate_server_add(
    owner_id: UUID,
    input_data: ServerInputGQL,
) -> ResultOrT[ShowtimesServer]:
    logger.info(f"Adding server for owner {owner_id}")
    owner_info = await ShowtimesUser.find_one(ShowtimesUser.user_id == owner_id)
    if not owner_info:
        logger.warning(f"Owner {owner_id} not found")
        return False, "Owner not found", ErrorCode.UserNotFound

    input_name: str | None = None
    if isinstance(input_data.name, str) and input_data.name.strip():
        input_name = input_data.name.strip()

    logger.info(f"Creating server with name {input_name}")
    if not isinstance(input_name, str):
        logger.warning("Invalid input, invalid/missing name")
        return False, "Invalid input, invalid/missing name", ErrorCode.ServerAddMissingName

    server_info = ShowtimesServer(name=input_name, owners=[to_link(owner_info)])
    if input_data.avatar is not None and input_data.avatar is not gql.UNSET:
        logger.debug(f"[{server_info.server_id}] Uploading avatar...")
        upload_result = await handle_image_upload(
            input_data.avatar,
            str(server_info.server_id),
            filename="avatar",
            type="servers",
        )

        server_info.avatar = ImageMetadata(
            type="servers",
            key=str(server_info.server_id),
            filename=upload_result.filename,
            parent=None,
        )
    if isinstance(input_data.integrations, list):
        await async_raise_for_invalid_integrations(input_data.integrations)
        add_integrations: list[IntegrationInputGQL] = []
        for idx, integration in enumerate(input_data.integrations):
            if not isinstance(integration, IntegrationInputGQL):
                raise TypeError(f"Integration[{idx}] must be an IntegrationInputGQL")

            if integration.action != IntegrationInputActionGQL.DELETE:
                add_integrations.append(integration)

        for integration in add_integrations:
            server_info.integrations.append(IntegrationId(id=integration.id, type=integration.type))

    logger.info(f"Saving server {server_info.server_id}")
    _server_info = await ShowtimesServer.insert_one(server_info)
    if _server_info is None:
        logger.error("Server creation failed")
        return False, "Server creation failed", ErrorCode.ServerError
    await update_searchdb(server_info)
    return True, _server_info, None


async def mutate_server_delete(
    server_id: UUID,
    owner_id: str | None = None,
) -> Result:
    logger.info(f"Updating server {server_id}")
    server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == server_id)

    if not server_info:
        logger.warning(f"Server {server_id} not found")
        return Result(success=False, message="Server not found", code=ErrorCode.ServerNotFound)

    owners = [owner.ref.id for owner in server_info.owners]
    if owner_id and ObjectId(owner_id) not in owners:
        logger.warning(f"Owner {owner_id} not found")
        return Result(
            success=False, message="You are not one of the owner of this server", code=ErrorCode.ServerNotAllowed
        )

    logger.info(f"Preparing for server deletion {server_id}...")
    project_ids = [project.ref.id for project in server_info.projects]
    async for project_info in ShowProject.find(OpIn(ShowProject.id, project_ids)):
        logger.info(f"Deleting project {project_info.show_id} from {server_id}...")
        await common_mutate_project_delete(project_info, server_info, skip_server_update=True)

    if server_info.avatar and server_info.avatar.type != "invalids":
        logger.debug(f"Deleting old avatar for server {server_id}")
        await delete_image_upload(server_info.avatar)

    logger.info(f"Deleting server {server_id}...")
    await delete_searchdb(server_info)
    await server_info.delete()  # type: ignore
    await TimeSeriesServerDelete.insert_one(TimeSeriesServerDelete(model_id=server_id))

    return Result(success=True, message="Server deleted", code=None)
