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

import asyncio
from uuid import UUID

from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn
from bson import ObjectId
from pydantic import BaseModel

from showtimes.controllers.searcher import get_searcher
from showtimes.controllers.storages import get_storage
from showtimes.graphql.models.common import IntegrationInputGQL
from showtimes.graphql.models.fallback import ErrorCode, Result
from showtimes.models.database import (
    DefaultIntegrationType,
    RoleActor,
    ShowProject,
    ShowtimesCollaborationLinkSync,
    ShowtimesServer,
    to_link,
)
from showtimes.models.searchdb import ProjectSearch
from showtimes.models.timeseries import TimeSeriesProjectDelete
from showtimes.tooling import get_logger

__all__ = (
    "raise_for_invalid_integrations",
    "async_raise_for_invalid_integrations",
    "query_aggregate_project_ids",
    "common_mutate_project_delete",
    "delete_project_searchdb",
)
logger = get_logger("Showtimes.GraphQL.Mutations.Common")


class SimpleProjectId(BaseModel):
    show_id: UUID
    server_id: UUID


def raise_for_invalid_integrations(integrations: list[IntegrationInputGQL]):
    for idx, integration in enumerate(integrations):
        if not integration.id.strip():
            raise ValueError(f"Integration[{idx}] has empty ID")
        if not DefaultIntegrationType.verify(integration.type):
            raise ValueError(f"Integration[{idx}] has unknown type: {integration.type}")


async def async_raise_for_invalid_integrations(integrations: list[IntegrationInputGQL]):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, raise_for_invalid_integrations, integrations)


async def query_aggregate_project_ids(project_ids: list[ObjectId]):
    results = await ShowProject.find(OpIn(ShowProject.id, project_ids)).project(SimpleProjectId).to_list()
    return results


async def delete_project_searchdb(project_id: UUID) -> None:
    logger.debug(f"Deleting Project Search Index for project {project_id}")
    searcher = get_searcher()
    await searcher.delete_document(ProjectSearch.Config.index, str(project_id))


async def common_mutate_project_delete(
    project_info: ShowProject,
    server_info: ShowtimesServer,
    *,
    skip_server_update: bool = False,
) -> Result:
    stor = get_storage()
    project_id = project_info.show_id
    logger.info(f"Deleting project {project_id} poster")
    if project_info.poster.image:
        # Check if type is invalids
        if project_info.poster.image.type != "invalids":
            await stor.delete(
                base_key=project_info.poster.image.key,
                parent_id=project_info.poster.image.parent,
                filename=project_info.poster.image.filename,
                type=project_info.poster.image.type,
            )

    collected_dbref: list[ObjectId] = []
    for assignee in project_info.assignments:
        if assignee.actor is not None:
            collected_dbref.append(assignee.actor.to_ref().id)

    logger.info(f"Deleting project {project_id} actors")
    await RoleActor.find(OpIn(RoleActor.id, collected_dbref)).delete_many()

    logger.info(f"Deleting project {project_id} from searchdb")
    await delete_project_searchdb(project_id)

    logger.info(f"Deleting project {project_id}")
    object_link = to_link(project_info)
    await project_info.delete()  # type: ignore

    # Unlink from server
    if not skip_server_update:
        projects = [project for project in server_info.projects if project.ref.id != object_link.ref.id]
        server_info.projects = projects
        await server_info.save()  # type: ignore

    # Unlink from collaboration/confirmation
    logger.info(f"Deleting project {project_id} from collaboration")
    collab_sync = await ShowtimesCollaborationLinkSync.find_one(
        OpAnd(
            OpIn(ShowtimesCollaborationLinkSync.projects, [project_id]),
            OpIn(ShowtimesCollaborationLinkSync.servers, [server_info.server_id]),
        ),
    )

    if collab_sync is not None:
        # Delete the UUID
        collab_sync.projects.remove(project_id)
        collab_sync.servers.remove(server_info.server_id)
        # Check if only single or empty
        if len(collab_sync.projects) <= 1 or len(collab_sync.servers) <= 1:
            # Delete link
            logger.info(f"Collaboration link {collab_sync.id} is no longer needed, deleting...")
            await collab_sync.delete()  # type: ignore
        else:
            await collab_sync.save()  # type: ignore

    # TODO: Delete confirmation

    await TimeSeriesProjectDelete.insert_one(
        TimeSeriesProjectDelete(model_id=project_id, server_id=server_info.server_id)
    )
    return Result(success=True, message="Project deleted", code=ErrorCode.Success)
