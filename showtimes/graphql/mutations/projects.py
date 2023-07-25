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

from dataclasses import dataclass, field
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Literal, TypeAlias, TypeVar, cast
from uuid import UUID

import aiohttp
import pendulum
import strawberry as gql
from beanie.operators import And as OpAnd
from beanie.operators import In as OpIn
from bson import ObjectId

from showtimes.controllers.anilist import (
    get_anilist_client,
    multiply_anilist_date,
    parse_anilist_fuzzy_date,
    rgbhex_to_rgbint,
)
from showtimes.controllers.gqlapi import GraphQLResult
from showtimes.controllers.searcher import get_searcher
from showtimes.controllers.storages import get_storage
from showtimes.extensions.graphql.files import delete_image_upload, handle_image_upload
from showtimes.graphql.models.common import IntegrationInputGQL
from showtimes.graphql.models.enums import (
    IntegrationInputActionGQL,
    ProjectInputAssigneeActionGQL,
    SearchExternalTypeGQL,
    SearchSourceTypeGQL,
)
from showtimes.graphql.models.fallback import ErrorCode, Result
from showtimes.graphql.models.projects import (
    ProjectEpisodeInput,
    ProjectInputAssigneeGQL,
    ProjectInputAssigneeInfoGQL,
    ProjectInputExternalGQL,
    ProjectInputGQL,
    ProjectInputRolesGQL,
)
from showtimes.models.anilist import (
    AnilistAiringScheduleNode,
    AnilistAnimeScheduleInfoResult,
    AnilistAnimeScheduleResult,
    AnilistQueryMediaX,
)
from showtimes.models.database import (
    DEFAULT_ROLES_MANGA,
    DEFAULT_ROLES_SHOWS,
    EpisodeStatus,
    ImageMetadata,
    IntegrationId,
    RoleActor,
    RoleStatus,
    ShowActor,
    ShowExternalAnilist,
    ShowExternalData,
    ShowExternalEpisode,
    ShowPoster,
    ShowProject,
    ShowtimesCollaborationLinkSync,
    ShowtimesServer,
    to_link,
)
from showtimes.models.searchdb import ProjectSearch, ServerSearch
from showtimes.models.timeseries import TimeSeriesProjectEpisodeChanges
from showtimes.tooling import get_logger
from showtimes.utils import complex_walk, make_uuid

__all__ = (
    "mutate_project_add",
    "mutate_project_update",
    "mutate_project_delete",
    "mutate_project_update_episode",
)
ResultT = TypeVar("ResultT")
ResultOrT: TypeAlias = tuple[Literal[False], str, str] | tuple[Literal[True], ResultT, None]
logger = get_logger("Showtimes.GraphQL.Mutations.Servers")


class AnilistQueryInfo(AnilistAnimeScheduleInfoResult):
    chapters: int | None
    volumes: int | None


ANILIST_QUERY = """
query shows($id:Int!) {
    Media(id:$id,type:ANIME) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        coverImage {
            extraLarge
            large
            medium
            color
        }
        format
        episodes
        chapters
        volumes
        startDate {
            year
            month
            day
        }
    }
}
query books($id:Int!) {
    Media(id:$id,type:MANGA) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        coverImage {
            extraLarge
            large
            medium
            color
        }
        format
        episodes
        chapters
        volumes
        startDate {
            year
            month
            day
        }
    }
}
query airingSchedule($id:Int!,$page:Int) {
    Media(id:$id,type:ANIME) {
        airingSchedule(page:$page,perPage:1) {
            nodes {
                id
                episode
                airingAt
            }
        }
    }
}
"""


async def _query_anilist_airing_schedules(media_id: str):
    client = get_anilist_client()
    current_page = 1

    def _paginate_fn(data: AnilistQueryMediaX[AnilistAnimeScheduleResult] | None):
        if data is None:
            return False, 1, "page"

        nodes_data = complex_walk(data, "Media.airingSchedule.nodes")
        if not nodes_data:
            return False, None, "page"
        return True, current_page + 1, "page"

    predicated = partial(_paginate_fn)
    joined_data: list[AnilistAiringScheduleNode] = []
    logger.debug(f"Querying Anilist Airing Schedules for {media_id} | Page {current_page}")
    async for raw_data in client.paginate(
        ANILIST_QUERY, {"id": int(media_id)}, operation_name="airingSchedule", predicate=predicated
    ):
        data = cast(GraphQLResult[AnilistQueryMediaX[AnilistAnimeScheduleInfoResult]], raw_data)
        if not data.data:
            break
        nodes = cast(list[AnilistAiringScheduleNode], complex_walk(data.data, "Media.airingSchedule.nodes"))
        if not nodes:
            break
        joined_data.extend(nodes)
        current_page += 1
        logger.debug(f"Querying Anilist Airing Schedules for {media_id} | Page {current_page}")
    logger.debug(f"Finished querying Anilist Airing Schedules for {media_id} | {len(joined_data)} results")
    return joined_data


@dataclass
class QueryResults:
    data: ShowExternalData
    title: str
    poster_url: str | None
    poster_color: int | None
    other_titles: list[str] = field(default_factory=list)


def _extended_episode_counter(
    external_episodes: list[ShowExternalEpisode], expected_count: int | None = None
) -> list[ShowExternalEpisode]:
    current_count = len(external_episodes)
    additional_episodes: list[ShowExternalEpisode] = []
    if expected_count is not None and expected_count > current_count:
        # Make more episodes
        last_ep_air = external_episodes[-1].airtime
        for episode in range(current_count, expected_count):
            act_eps = episode - current_count + 1
            additional_episodes.append(
                ShowExternalEpisode(
                    episode=act_eps + 1,
                    airtime=multiply_anilist_date(
                        int(last_ep_air),
                        act_eps,
                    ).float_timestamp,
                )
            )
    return additional_episodes


async def _query_anilist_info_or_db(
    media_id: str, expected_count: int | None, type: SearchExternalTypeGQL
) -> Result | QueryResults:
    if type == SearchExternalTypeGQL.UNKNOWN:
        return Result(success=False, message="Unknown search type", code="COMMON_SEARCH_UNKNOWN_TYPE")
    act_type = type.value
    if type == SearchExternalTypeGQL.MOVIE:
        act_type = "shows"
    anilist_client = get_anilist_client()

    responses = await anilist_client.handle(ANILIST_QUERY, {"id": int(media_id)}, operation_name=act_type)
    if responses is None:
        return Result(success=False, message="Anilist API is down", code=ErrorCode.AnilistAPIUnavailable)

    if responses.data is None:
        return Result(success=False, message="Invalid results!", code=ErrorCode.AnilistAPIError)

    response_data = cast(AnilistQueryMediaX[AnilistQueryInfo], responses.data)
    media: AnilistQueryInfo | None = response_data.Media
    if not media:
        return Result(success=False, message="No results found!", code=ErrorCode.AnilistAPIError)

    db_data = await ShowExternalAnilist.find_one(ShowExternalAnilist.ani_id == str(media_id))
    title_aliases = [media.title.romaji, media.title.english, media.title.native]
    selected_title = media.title.romaji or media.title.english or media.title.native
    title_aliases.remove(selected_title)
    if db_data is not None:
        db_data.episodes.extend(_extended_episode_counter(db_data.episodes, expected_count))
        return QueryResults(
            data=db_data,
            title=selected_title,
            poster_url=media.coverImage.extraLarge or media.coverImage.large or media.coverImage.medium,
            poster_color=rgbhex_to_rgbint(media.coverImage.color),
            other_titles=title_aliases,
        )

    if expected_count is None:
        expected_count = media.episodes or media.chapters or media.volumes

    start_time = parse_anilist_fuzzy_date(media.startDate)
    airing_schedules: list[AnilistAiringScheduleNode] | None = None
    if type in [SearchExternalTypeGQL.MOVIE, SearchExternalTypeGQL.SHOWS]:
        airing_schedules = await _query_anilist_airing_schedules(media_id)
    if airing_schedules:
        start_time = pendulum.from_timestamp(airing_schedules[0].airingAt)
    if start_time is None:
        return Result(
            success=False,
            message="Unable to add project because of an unknown start time!",
            code=ErrorCode.ProjectAddStartTimeUnknown,
        )
    external_episodes: list[ShowExternalEpisode] = []
    if airing_schedules is not None:
        for episode in airing_schedules:
            external_episodes.append(
                ShowExternalEpisode(
                    episode=episode.episode,
                    airtime=float(episode.airingAt),
                )
            )
    else:
        episode_count = media.episodes or media.chapters or media.volumes or expected_count or 1
        for episode in range(episode_count):
            external_episodes.append(
                ShowExternalEpisode(
                    episode=episode + 1,
                    airtime=multiply_anilist_date(
                        int(start_time.timestamp()),
                        episode + 1,
                    ).float_timestamp,
                )
            )

    external_episodes.extend(_extended_episode_counter(external_episodes, expected_count))

    return QueryResults(
        data=ShowExternalAnilist(
            ani_id=str(media.id),
            mal_id=str(media.idMal) if media.idMal is not None else None,
            episodes=external_episodes,
            start_time=start_time.timestamp(),
        ),
        title=selected_title,
        poster_url=media.coverImage.extraLarge or media.coverImage.large or media.coverImage.medium,
        poster_color=rgbhex_to_rgbint(media.coverImage.color),
        other_titles=title_aliases,
    )


async def update_searchdb(project: ShowProject) -> None:
    logger.debug(f"Updating Project Search Index for project {project.show_id}")
    searcher = get_searcher()
    await searcher.update_document(ProjectSearch.from_db(project))


async def update_server_searchdb(server: ShowtimesServer) -> None:
    logger.debug(msg=f"Updating Server Search Index for server {server.server_id}")
    searcher = get_searcher()
    await searcher.update_document(ServerSearch.from_db(server))


async def delete_searchdb(project_id: UUID) -> None:
    logger.debug(f"Deleting Project Search Index for project {project_id}")
    searcher = get_searcher()
    await searcher.delete_document(ProjectSearch.Config.index, str(project_id))


def _process_input_integration(integrations: list[IntegrationInputGQL] | None):
    if integrations is None:
        return []
    if integrations is gql.UNSET:
        return []

    return [
        IntegrationId(id=integration.id, type=integration.type)
        for integration in integrations
        if integration.action == IntegrationInputActionGQL.ADD
    ]


async def _find_project(project_id: UUID, owner_id: str | None = None) -> Result | tuple[ShowProject, ShowtimesServer]:
    logger.info(f"Finding project for {project_id}")

    project_info = await ShowProject.find_one(ShowProject.show_id == project_id)
    if not project_info:
        logger.warning(f"Project {project_id} not found")
        return Result(success=False, message="Project not found", code=ErrorCode.ProjectNotFound)

    server_info = await ShowtimesServer.find_one(ShowtimesServer.server_id == project_info.server_id)
    if not server_info:
        logger.warning(f"Server {project_info.server_id} not found")
        return Result(success=False, message="Linked server not found", code=ErrorCode.ServerNotFound)

    owners = [owner.ref.id for owner in server_info.owners]
    if owner_id and ObjectId(owner_id) not in owners:
        logger.warning(f"Owner {owner_id} not found")
        return Result(
            success=False, message="You are not one of the owner of this server", code=ErrorCode.ServerNotAllowed
        )

    return project_info, server_info


async def mutate_project_delete(
    project_id: UUID,
    owner_id: str | None = None,  # None assumes admin
) -> Result:
    stor = get_storage()
    find_results = await _find_project(project_id, owner_id)
    if isinstance(find_results, Result):
        return find_results

    project_info, server_info = find_results

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
    await delete_searchdb(project_id)

    logger.info(f"Deleting project {project_id}")
    object_link = to_link(project_info)
    await project_info.delete()  # type: ignore

    # Unlink from server
    projects = [project for project in server_info.projects if project.ref.id != object_link.ref.id]
    server_info.projects = projects
    await server_info.save()  # type: ignore

    logger.info(f"Updating server {server_info.server_id} searchdb")
    await update_server_searchdb(server_info)

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

    return Result(success=True, message="Project deleted", code=ErrorCode.Success)


async def mutate_project_add(
    server_id: UUID,
    input_data: ProjectInputGQL,
    owner_id: str | None = None,  # None assumes admin
) -> Result | ShowProject:
    logger.info(f"Adding project for owner {owner_id} and {server_id}")

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

    if not isinstance(input_data.external, ProjectInputExternalGQL):
        logger.warning("External data is required for project creation!")
        return Result(
            success=False,
            message="External data is required for project creation!",
            code=ErrorCode.ProjectAddMissingExternal,
        )

    # XXX: Implement TMDb handling later
    external = input_data.external
    match external.source:
        case SearchSourceTypeGQL.ANILIST:
            logger.info(f"Querying Anilist for {external.ref}")
            source_info = await _query_anilist_info_or_db(external.ref, input_data.count, external.type)
        case _:
            return Result(
                success=False, message="Unsupported external source", code=ErrorCode.ProjectAddUnsupportedExternal
            )

    if isinstance(source_info, Result):
        logger.warning(f"Anilist query failed: {source_info.message}")
        return source_info

    ext_info: ShowExternalData = source_info.data
    await ext_info.save()  # type: ignore

    project_id = make_uuid()

    project_aliases: list[str] = source_info.other_titles
    if isinstance(input_data.aliases, list):
        for alias in input_data.aliases:
            if isinstance(alias, str) and alias not in project_aliases:
                project_aliases.append(alias)

    roles_selections: list[RoleStatus] = (
        DEFAULT_ROLES_SHOWS if external.type != SearchExternalTypeGQL.BOOKS else DEFAULT_ROLES_MANGA
    )
    if isinstance(input_data.roles, list):
        logger.debug("Using custom roles")
        user_modes: list[RoleStatus] = []
        for role in input_data.roles:
            if not isinstance(role, ProjectInputRolesGQL):
                continue
            user_modes.append(
                RoleStatus(
                    key=role.key.upper(),
                    name=role.name,
                )
            )
        if user_modes:
            roles_selections = user_modes

    use_assignee: list[ShowActor] = []
    if isinstance(input_data.assignees, list):
        added_actor: dict[str, RoleActor] = {}
        logger.info(f"Adding {len(input_data.assignees)} assignees")
        for assignee in input_data.assignees:
            if not isinstance(assignee, ProjectInputAssigneeGQL):
                continue

            ainfo: RoleActor | None = None
            if isinstance(assignee.info, ProjectInputAssigneeInfoGQL):
                integrations = _process_input_integration(assignee.info.integrations)
                if assignee.info.id in added_actor:
                    ainfo = added_actor[assignee.info.id]
                    # Update integrations
                    for integration in integrations:
                        # Injected
                        inject = False
                        for idx, _integration in enumerate(ainfo.integrations):
                            if _integration.id == integration.id:
                                ainfo.integrations[idx] = integration
                                inject = True
                                break
                        if not inject:
                            ainfo.integrations.append(integration)
                    await ainfo.save()  # type: ignore
                    added_actor[assignee.info.id] = ainfo
                else:
                    ainfo = RoleActor(
                        name=assignee.info.name,
                        integrations=integrations,
                    )
                    await ainfo.save()  # type: ignore
                    added_actor[assignee.info.id] = ainfo

            use_assignee.append(
                ShowActor(
                    key=assignee.key.upper(),
                    actor=to_link(ainfo) if ainfo else None,
                )
            )
    else:
        logger.warning(f"Using default assignees for {project_id}")
        for role in roles_selections:
            use_assignee.append(
                ShowActor(
                    key=role.key,
                )
            )

    statuses: list[EpisodeStatus] = []
    for episode in ext_info.episodes:
        statuses.append(
            EpisodeStatus(
                episode=episode.episode,
                is_released=False,
                airing_at=episode.airtime,
                statuses=roles_selections,
            )
        )

    poster_meta: ImageMetadata | None = None
    if input_data.poster is not None and input_data.poster is not gql.UNSET:
        logger.debug(f"[{server_info.server_id}][{project_id}] Uploading poster...")
        upload_result = await handle_image_upload(
            input_data.poster,
            str(server_info.server_id),
            parent_id=str(project_id),
            filename="poster",
            type="project",
        )

        poster_ext = Path(upload_result.filename).suffix
        poster_meta = ImageMetadata(
            key=str(server_info.server_id),
            parent=str(project_id),
            filename=upload_result.filename,
            type="project",
            format=poster_ext,
        )
    else:
        if source_info.poster_url:
            logger.debug(f"[{server_info.server_id}][{project_id}] Downloading poster from source...")
            async with aiohttp.ClientSession() as session:
                async with session.get(source_info.poster_url) as resp:
                    resp.raise_for_status()

                    bytes_data = await resp.read()

            file_ext = Path(source_info.poster_url).suffix
            bytes_io = BytesIO(bytes_data)
            bytes_io.seek(0)
            logger.debug(f"[{server_info.server_id}][{project_id}] Uploading poster from source...")

            stor = get_storage()
            result = await stor.stream_upload(
                base_key=str(server_info.server_id),
                parent_id=str(project_id),
                filename=f"poster{file_ext}",
                type="project",
                data=bytes_io,
            )
            if result is None:
                return Result(
                    success=False,
                    message="Unable to upload poster from source",
                    code=ErrorCode.ImageUploadFailed,
                )

            if file_ext.startswith("."):
                file_ext = file_ext[1:]
            poster_meta = ImageMetadata(
                key=str(server_info.server_id),
                parent=str(project_id),
                filename=f"poster.{file_ext}",
                type="project",
                format=file_ext,
            )

    if poster_meta is None:
        logger.warning(f"[{server_info.server_id}][{project_id}] Unable to get poster metadata, using default...")
        poster_meta = ImageMetadata(
            key="project",
            filename="default.png",
            parent=None,
            type="invalids",
            format="png",
        )

    project = ShowProject(
        title=source_info.title,
        poster=ShowPoster(image=poster_meta, color=source_info.poster_color),
        external=to_link(ext_info),
        server_id=server_id,
        assignments=use_assignee,
        statuses=statuses,
        show_id=project_id,
        integrations=_process_input_integration(input_data.integrations),
        aliases=project_aliases,
    )

    logger.info(f"Saving project {project_id}")
    _project = await ShowProject.insert_one(project)
    if _project is None:
        return Result(success=False, message="Unable to save project", code=ErrorCode.ServerError)
    logger.info(f"Project {project_id} saved, updating searchdb")
    await update_searchdb(project)
    logger.info(f"Updating server {server_info.server_id} searchdb")
    server_info.projects.append(to_link(project))
    await server_info.save()  # type: ignore
    await update_server_searchdb(server_info)
    return _project


async def mutate_project_update(
    project_id: UUID,
    input_data: ProjectInputGQL,
    owner_id: str | None = None,  # None assumes admin
) -> Result | ShowProject:
    logger.info(f"Modifying project {project_id}")

    find_results = await _find_project(project_id, owner_id)
    if isinstance(find_results, Result):
        return find_results
    project_info, server_info = find_results

    save_changes = False

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
            for int_integ in project_info.integrations:
                if int_integ.id == integration.id and int_integ.type == integration.type:
                    _found_idx = project_info.integrations.index(int_integ)
                    break

            if _found_idx is not None:
                save_changes = True
                project_info.integrations.pop(_found_idx)

        for integration in add_integrations:
            project_info.integrations.append(IntegrationId(id=integration.id, type=integration.type))

        for integration in modify_integrations:
            found_any = False
            for idx, proj_integration in enumerate(project_info.integrations):
                if proj_integration.type == integration.type and proj_integration.id != integration.id:
                    project_info.integrations[idx].id = integration.id
                    found_any = True
                    break
            if not found_any:
                project_info.integrations.append(IntegrationId(id=integration.id, type=integration.type))
            save_changes = True

    if isinstance(input_data.aliases, list):
        project_info.aliases = input_data.aliases

    delete_show_actor: list[ShowActor] = []
    if isinstance(input_data.assignees, list):
        preexisting_assigness: dict[str, RoleActor] = {}
        for assignee in project_info.assignments:
            if assignee.actor is not None:
                fetched = await assignee.actor.fetch()
                if isinstance(fetched, RoleActor):
                    preexisting_assigness[str(fetched.actor_id)] = fetched
                else:
                    logger.warning(f"Unable to fetch actor {assignee.actor.ref.id}, deleting info")
                    assignee.actor = None
                    save_changes = True

        for assignee_new in input_data.assignees:
            if not isinstance(assignee_new, ProjectInputAssigneeGQL):
                continue
            for old_assignee in project_info.assignments:
                if old_assignee.key == assignee_new.key.upper():
                    if assignee_new.mode == ProjectInputAssigneeActionGQL.DELETE:
                        delete_show_actor.append(old_assignee)
                    elif assignee_new.mode == ProjectInputAssigneeActionGQL.UPSERT:
                        # If info is None, then remove it
                        if assignee_new.info is None and old_assignee.actor is not None:
                            old_assignee.actor = None
                            save_changes = True
                        elif assignee_new.info is not None and old_assignee.actor is None:
                            integrations = _process_input_integration(assignee_new.info.integrations)
                            preext = preexisting_assigness.get(assignee_new.info.id)
                            if preext is not None:
                                # Update integrations
                                for integration in integrations:
                                    # Injected
                                    inject = False
                                    for idx, _integration in enumerate(preext.integrations):
                                        if _integration.id == integration.id:
                                            preext.integrations[idx] = integration
                                            inject = True
                                            break
                                    if not inject:
                                        preext.integrations.append(integration)
                                await preext.save()  # type: ignore
                                old_assignee.actor = to_link(preext)
                                save_changes = True
                                preexisting_assigness[str(preext.actor_id)] = preext
                            else:
                                ainfo = RoleActor(
                                    name=assignee_new.info.name,
                                    integrations=integrations,
                                )
                                await ainfo.save()  # type: ignore
                                preexisting_assigness[str(assignee_new.info.id)] = ainfo
                                save_changes = True

    if delete_show_actor:
        logger.info(f"Deleting {len(delete_show_actor)} actors")
        for actor in delete_show_actor:
            for status in project_info.statuses:
                delete_idx: int | None = None
                for idx, role in enumerate(status.statuses):
                    if role.key == actor.key.upper():
                        delete_idx = idx
                        break
                if delete_idx is not None:
                    status.statuses.pop(delete_idx)
                    save_changes = True
            delete_idx_a: int | None = None
            for idx, assignee in enumerate(project_info.assignments):
                if assignee.key == actor.key.upper():
                    delete_idx_a = idx
                    break
            if delete_idx_a is not None:
                project_info.assignments.pop(delete_idx_a)
                save_changes = True

    poster_meta: ImageMetadata | None = None
    if input_data.poster is not None and input_data.poster is not gql.UNSET:
        logger.debug(f"[{project_info.server_id}][{project_id}] Uploading poster...")
        upload_result = await handle_image_upload(
            input_data.poster,
            str(server_info.server_id),
            parent_id=str(project_id),
            filename="poster",
            type="project",
        )

        poster_ext = Path(upload_result.filename).suffix
        poster_meta = ImageMetadata(
            key=str(project_info.server_id),
            parent=str(project_id),
            filename=upload_result.filename,
            type="project",
            format=poster_ext,
        )

    if poster_meta is not None:
        logger.info(f"Updating project {project_id} poster")
        if project_info.poster.image.type != "invalids":
            logger.debug(f"Deleting old poster for project {project_id}")
            await delete_image_upload(project_info.poster.image)
        project_info.poster.image = poster_meta
        save_changes = True

    if save_changes:
        logger.info(f"Updating project {project_id}")
        await project_info.save()  # type: ignore
        logger.info(f"Project {project_id} updated, updating searchdb")
        await update_searchdb(project_info)
    return project_info


def _create_updated_statuses(
    old_status: EpisodeStatus, episode_input: ProjectEpisodeInput
) -> tuple[EpisodeStatus, bool]:
    new_status = old_status.copy()
    has_changed = False
    if isinstance(episode_input.delay_reason, str) and episode_input.delay_reason.strip():
        new_status.delay_reason = episode_input.delay_reason
        has_changed = True

    if isinstance(episode_input.release, bool) and episode_input.release != old_status.is_released:
        new_status.is_released = episode_input.release
        has_changed = True

    if isinstance(episode_input.roles, list):
        for role in episode_input.roles:
            if not isinstance(role, ProjectInputRolesGQL):
                continue
            for status in new_status.statuses:
                if status.key == role.key.upper() and status.finished != role.value:
                    status.finished = role.value
                    has_changed = True
                    break

    return new_status, has_changed


async def mutate_project_update_episode(
    project_id: UUID,
    episodes: list[ProjectEpisodeInput],
    owner_id: str | None = None,  # None assumes admin
):
    if not episodes:
        return Result(success=False, message="No episodes to update", code=ErrorCode.ProjectUpdateNoEpisode)
    find_results = await _find_project(project_id, owner_id)
    if isinstance(find_results, Result):
        return find_results

    project_info, _ = find_results

    logger.info(f"Updating project {project_id} episodes")
    all_statuses = project_info.statuses

    changed_statuses: list[EpisodeStatus] = []
    old_statuses: list[EpisodeStatus] = []
    for episode in episodes:
        index = await project_info.async_get_episode_index(episode.episode)
        if index is None:
            continue
        update, status_ch = _create_updated_statuses(all_statuses[index], episode)
        if status_ch:
            old_statuses.append(project_info.statuses[index].copy())
            project_info.statuses[index] = update
            changed_statuses.append(update)

    if not changed_statuses:
        return Result(success=False, message="No episodes to update", code=ErrorCode.ProjectUpdateNoEpisode)

    await project_info.save()  # type: ignore

    ts_changes = TimeSeriesProjectEpisodeChanges(
        model_id=project_id,
        server_id=project_info.server_id,
        old=old_statuses,
        new=changed_statuses,
    )
    await TimeSeriesProjectEpisodeChanges.insert_one(ts_changes)
    await update_searchdb(project_info)
    return Result(success=True, message="Episodes updated", code=ErrorCode.Success)
