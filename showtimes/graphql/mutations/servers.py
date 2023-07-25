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

from showtimes.controllers.searcher import get_searcher
from showtimes.extensions.graphql.files import delete_image_upload, handle_image_upload
from showtimes.graphql.models.common import IntegrationInputGQL
from showtimes.graphql.models.enums import IntegrationInputActionGQL
from showtimes.graphql.models.fallback import ErrorCode
from showtimes.graphql.models.servers import ServerInputGQL
from showtimes.models.database import ImageMetadata, IntegrationId, ShowtimesServer, ShowtimesUser, to_link
from showtimes.models.searchdb import ServerSearch
from showtimes.tooling import get_logger

__all__ = (
    "mutate_server_update",
    "mutate_server_add",
)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]
logger = get_logger("Showtimes.GraphQL.Mutations.Servers")


async def update_searchdb(server: ShowtimesServer) -> None:
    logger.debug(f"Updating Server Search Index for server {server.server_id}")
    searcher = get_searcher()
    await searcher.update_document(ServerSearch.from_db(server))


async def mutate_server_update(
    id: UUID,
    input_data: ServerInputGQL,
) -> ResultOrT[ShowtimesServer]:
    logger.info(f"Updating server {id}")
    server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == id)

    if not server_info:
        logger.warning(f"Server {id} not found")
        return False, "Server not found", ErrorCode.ServerNotFound

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
        return False, "Invalid input, invalid/missing name", ErrorCode.ServerAddMissingNmae

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
