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

from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Any, TypeAlias, TypeVar
from uuid import UUID

import httpx
import pendulum
from beanie import Document, Link, free_fall_migration
from pendulum.datetime import DateTime
from pydantic import BaseModel, Field

from showtimes.controllers.searcher import get_searcher, init_searcher
from showtimes.controllers.security import encrypt_password
from showtimes.controllers.storages import get_s3_storage, get_storage, init_s3_storage
from showtimes.models import database as newdb
from showtimes.models.searchdb import ProjectSearch, ServerSearch, UserSearch
from showtimes.tooling import get_env_config, setup_logger
from showtimes.utils import make_uuid, try_int

CURRENT_DIR = Path(__file__).absolute().parent
ROOT_DIR = CURRENT_DIR.parent
logger = setup_logger(ROOT_DIR / "logs" / "migrations.log")
_COVER_CACHE: dict[str, bytes] = {}


# Old DB Schemas
# https://github.com/naoTimesdev/naoTimes/blob/rewrite/naotimes/models/showtimes.py
class EpisodeStatusCustomProgressSchema(BaseModel):
    key: str
    name: str
    done: bool = Field(default=False)


class EpisodeStatusProgressSchema(BaseModel):
    TL: bool = Field(default=False)
    TLC: bool = Field(default=False)
    ENC: bool = Field(default=False)
    ED: bool = Field(default=False)
    TM: bool = Field(default=False)
    TS: bool = Field(default=False)
    QC: bool = Field(default=False)
    custom: list[EpisodeStatusCustomProgressSchema] = Field(default_factory=list)


class EpisodeStatusSchema(BaseModel):
    episode: int
    is_done: bool
    progress: EpisodeStatusProgressSchema = Field(default_factory=EpisodeStatusProgressSchema)
    airtime: int | float | None = Field(default=None)
    delay_reason: str | None = Field(default=None)


class ShowAnimeAssigneeSchema(BaseModel):
    id: str | None = Field(default=None)
    name: str | None = Field(default=None)


class ShowAnimeAssigneeCustomSchema(BaseModel):
    key: str
    name: str
    person: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)


class ShowAnimeAssignmentsSchema(BaseModel):
    TL: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TLC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    ENC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    ED: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TM: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    TS: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    QC: ShowAnimeAssigneeSchema = Field(default_factory=ShowAnimeAssigneeSchema)
    custom: list[ShowAnimeAssigneeCustomSchema] = Field(default_factory=list)


class ShowAnimePosterSchema(BaseModel):
    url: str
    color: int | float | None = Field(default=None)


class ShowAnimeFSDBSchema(BaseModel):
    id: int | None
    ani_id: int | None


class ShowAnimeSchema(BaseModel):
    id: str
    mal_id: int | None
    title: str
    role_id: str | None
    start_time: int | float | None
    assignments: ShowAnimeAssignmentsSchema = Field(default_factory=ShowAnimeAssignmentsSchema)
    status: list[EpisodeStatusSchema] = Field(default_factory=list)
    poster_data: ShowAnimePosterSchema
    fsdb_data: ShowAnimeFSDBSchema | None = Field(default=None)
    aliases: list[str] = Field(default_factory=list)
    kolaborasi: list[str] = Field(default_factory=list)
    last_update: int | float


class ShowtimesCollabConfirmSchema(BaseModel):
    id: str
    server_id: str
    anime_id: str


class ShowtimesSchema(Document):
    # id: str
    # Bind the _id to mongo_id
    # mongo_id: ObjectId = Field(primary_field=True)
    # id: str
    srv_id: str
    name: str | None
    fsdb_id: int | None
    serverowner: list[str] = Field(default_factory=list)
    announce_channel: str | None
    anime: list[ShowAnimeSchema] = Field(default_factory=list)
    konfirmasi: list[ShowtimesCollabConfirmSchema] = Field(default_factory=list)

    class Settings:
        name = "showtimesdatas"

    class Config:
        fields = {"srv_id": "id", "id": "_id"}  # noqa: RUF012


class ShowAdminSchema(Document):
    admin_id: str
    # Bind the _id to mongo_id
    servers: list[str] = Field(default_factory=list)

    class Settings:
        name = "showtimesadmin"

    class Config:
        fields = {"admin_id": "id", "id": "_id"}  # noqa: RUF012


class ShowUIPrivilege(str, Enum):
    ADMIN = "owner"
    SERVER = "server"

    def to_newdb(self) -> newdb.UserType:
        if self == ShowUIPrivilege.ADMIN:
            return newdb.UserType.ADMIN
        elif self == ShowUIPrivilege.SERVER:
            return newdb.UserType.USER
        raise ValueError(f"Invalid privilege {self}")


class ShowUIUserType(str, Enum):
    DISCORD = "DISCORD"
    SERVER = "PASSWORD"


class ShowUIDiscordMeta(BaseModel):
    id: str
    name: str
    access_token: str
    refresh_token: str
    expires_at: int


class ShowtimesUISchema(Document):
    # srv_id = Field()
    # Bind the _id to mongo_id
    server_id: str
    secret: str
    name: str | None = Field(default=None)
    privilege: ShowUIPrivilege = Field(default=ShowUIPrivilege.SERVER)
    discord_meta: ShowUIDiscordMeta | None = Field(default=None)
    user_type: ShowUIUserType = Field(default=ShowUIUserType.SERVER)

    class Settings:
        name = "showtimesuilogin"

    class Config:
        fields: dict[str, str] = {"server_id": "id", "id": "_id"}  # noqa: RUF012


def int_or_none(value: str | float | int | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def str_or_none(value: Any | None) -> str | None:
    if value is None:
        return None
    return str(value)


ServerId: TypeAlias = str
ProjectId: TypeAlias = str
UsersHolder: TypeAlias = dict[str, newdb.ShowtimesUserGroup]
RolesHolder: TypeAlias = dict[str, newdb.RoleActor]
ProjectHolder: TypeAlias = dict[ProjectId, newdb.ShowProject]
CollabHolder: TypeAlias = dict[ServerId, list[tuple[ProjectId, list[ServerId]]]]
DocT = TypeVar("DocT", bound=Document)


def to_link(doc: DocT) -> Link[DocT]:
    dbref = doc.to_ref()
    return Link(ref=dbref, model_class=doc.__class__)


async def _upload_poster(server_id: str, project_id: str, poster: ShowAnimePosterSchema):
    global _COVER_CACHE

    stor = get_storage()

    logger.info(f"    Checking poster cache for {poster.url}...")
    bytes_data = _COVER_CACHE.get(poster.url)
    if bytes_data is None:
        logger.info(f"     Downloading poster from {poster.url}...")
        async with httpx.AsyncClient() as session:
            resp = await session.get(poster.url)
            resp.raise_for_status()

            bytes_data = await resp.aread()
            _COVER_CACHE[poster.url] = bytes_data

    poster_ext = Path(poster.url).suffix
    bytes_io = BytesIO(bytes_data)
    bytes_io.seek(0)
    logger.info(f"    Uploading poster{poster_ext}...")
    result = await stor.stream_upload(
        server_id,
        project_id,
        f"poster{poster_ext}",
        bytes_io,
        type="project",
    )
    if result is None:
        raise RuntimeError("Failed to upload poster")

    if poster_ext.startswith("."):
        poster_ext = poster_ext[1:]

    return newdb.ShowPoster(
        image=newdb.ImageMetadata(
            type="project",
            key=server_id,
            parent=project_id,
            filename=f"poster.{poster_ext}",
            format=poster_ext,
        ),
        color=int_or_none(poster.color),
    )


def is_valid_snowflake(value: str):
    # Naive check
    if not isinstance(value, str):
        return False
    if not value.isnumeric():
        return False
    if (val_int := try_int(value)) is None:
        return False

    if val_int < 4194304:
        return False
    return True


async def _get_actor_or_create(
    assigned_id: str | None,
    assigned_name: str | None,
    users: UsersHolder,
    actors: RolesHolder,
    *,
    session,
) -> tuple[Link[newdb.RoleActor] | None, RolesHolder]:
    if assigned_id is None:
        return None, actors

    if not is_valid_snowflake(assigned_id):
        return None, actors

    if assigned_id in actors:
        return to_link(actors[assigned_id]), actors

    integrations = [
        newdb.IntegrationId(id=str(assigned_id), type=newdb.DefaultIntegrationType.DiscordUser),
    ]
    if assigned_id in users:
        integrations.append(
            newdb.IntegrationId(id=str(users[assigned_id].user_id), type=newdb.DefaultIntegrationType.ShowtimesUser),
        )
    roleact = newdb.RoleActor(
        name=assigned_name or assigned_id,
        integrations=integrations,
    )
    _new_actor = await newdb.RoleActor.insert_one(roleact, session=session)
    if _new_actor is None:
        raise RuntimeError("Failed to add role actor")
    actors[assigned_id] = _new_actor
    return to_link(_new_actor), actors


async def _process_showtimes_project_assignments(
    assigness: ShowAnimeAssignmentsSchema, users: UsersHolder, actors: RolesHolder, *, session
):
    TLActor, actors = await _get_actor_or_create(
        assigness.TL.id,
        assigness.TL.name,
        users,
        actors,
        session=session,
    )
    TLCActor, actors = await _get_actor_or_create(
        assigness.TLC.id,
        assigness.TLC.name,
        users,
        actors,
        session=session,
    )
    ENCActor, actors = await _get_actor_or_create(
        assigness.ENC.id,
        assigness.ENC.name,
        users,
        actors,
        session=session,
    )
    EDActor, actors = await _get_actor_or_create(
        assigness.ED.id,
        assigness.ED.name,
        users,
        actors,
        session=session,
    )
    TSActor, actors = await _get_actor_or_create(
        assigness.TS.id,
        assigness.TS.name,
        users,
        actors,
        session=session,
    )
    TMActor, actors = await _get_actor_or_create(
        assigness.TM.id,
        assigness.TM.name,
        users,
        actors,
        session=session,
    )
    QCActor, actors = await _get_actor_or_create(
        assigness.QC.id,
        assigness.QC.name,
        users,
        actors,
        session=session,
    )

    show_actors: list[newdb.ShowActor] = []
    show_actors.append(newdb.ShowActor(actor=TLActor, key="TL"))
    show_actors.append(newdb.ShowActor(actor=TLCActor, key="TLC"))
    show_actors.append(newdb.ShowActor(actor=ENCActor, key="ENC"))
    show_actors.append(newdb.ShowActor(actor=EDActor, key="ED"))
    show_actors.append(newdb.ShowActor(actor=TSActor, key="TS"))
    show_actors.append(newdb.ShowActor(actor=TMActor, key="TM"))
    show_actors.append(newdb.ShowActor(actor=QCActor, key="QC"))
    INVALID_CUSTOM = ["TL", "TLC", "ENC", "ED", "TS", "TM", "QC"]
    for custom in assigness.custom:
        if custom.key in INVALID_CUSTOM:
            logger.warning(f"  Invalid custom key {custom.key}, skipping...")
        custom_actor, actors = await _get_actor_or_create(
            custom.person.id,
            custom.person.name,
            users,
            actors,
            session=session,
        )
        show_actors.append(newdb.ShowActor(actor=custom_actor, key=custom.key))
    return show_actors, actors


async def _process_role_status(
    status: EpisodeStatusProgressSchema, assignees: list[newdb.ShowActor]
) -> list[newdb.RoleStatus]:
    assigness_kv = {assignee.key: assignee for assignee in assignees}

    role_statuses: list[newdb.RoleStatus] = []
    if assigness_kv.get("TL") is not None:
        role_statuses.append(newdb.RoleStatus(key="TL", name="Translator", finished=status.TL))
    if assigness_kv.get("TLC") is not None:
        role_statuses.append(newdb.RoleStatus(key="TLC", name="Translation Checker", finished=status.TLC))
    if assigness_kv.get("ENC") is not None:
        role_statuses.append(newdb.RoleStatus(key="ENC", name="Encoder", finished=status.ENC))
    if assigness_kv.get("ED") is not None:
        role_statuses.append(newdb.RoleStatus(key="ED", name="Editor", finished=status.ED))
    if assigness_kv.get("TS") is not None:
        role_statuses.append(newdb.RoleStatus(key="TS", name="Typesetter", finished=status.TS))
    if assigness_kv.get("TM") is not None:
        role_statuses.append(newdb.RoleStatus(key="TM", name="Timer", finished=status.TM))
    if assigness_kv.get("QC") is not None:
        role_statuses.append(newdb.RoleStatus(key="QC", name="Quality Checker", finished=status.QC))

    INVALID_KEYS = ["TL", "TLC", "ENC", "ED", "TS", "TM", "QC"]
    for custom in status.custom:
        if custom.key in INVALID_KEYS:
            logger.warning(f"  Invalid custom key {custom.key}, skipping...")
        role_statuses.append(newdb.RoleStatus(key=custom.key, name=custom.name, finished=custom.done))
    return role_statuses


async def _process_showtimes_project_episodes(statusees: list[EpisodeStatusSchema], assignees: list[newdb.ShowActor]):
    episodes: list[newdb.EpisodeStatus] = []

    for status in statusees:
        episode = newdb.EpisodeStatus(
            episode=status.episode,
            is_released=status.is_done,
            airing_at=status.airtime,
            statuses=await _process_role_status(status.progress, assignees),
            delay_reason=status.delay_reason,
        )
        episodes.append(episode)
    return episodes


async def _process_showtimes_project_external_data(project: ShowAnimeSchema, *, session):
    res = await newdb.ShowExternalAnilist.find_one(newdb.ShowExternalAnilist.ani_id == str(project.id))
    if res is not None:
        return res

    episode_data: list[newdb.ShowExternalEpisode] = []
    for status in project.status:
        airtime = pendulum.now(tz="UTC").timestamp()
        if status.airtime is not None:
            airtime = float(status.airtime)
        episode_data.append(
            newdb.ShowExternalEpisode(
                episode=status.episode,
                airtime=airtime,
            )
        )
    new_data = newdb.ShowExternalAnilist(
        episodes=episode_data,
        ani_id=str(project.id),
        mal_id=str_or_none(project.mal_id),
        start_time=int_or_none(project.start_time),
    )
    _new_data = await newdb.ShowExternalAnilist.insert_one(new_data, session=session)
    if _new_data is None:
        raise RuntimeError("Failed to add external data")
    return _new_data


async def _process_showtimes_project(
    server_id: UUID, showanime: ShowAnimeSchema, users: UsersHolder, *, session
) -> newdb.ShowProject:
    show_id = make_uuid()
    ssposter = await _upload_poster(str(server_id), str(show_id), showanime.poster_data)

    integrations = [
        newdb.IntegrationId(id=str(showanime.role_id), type=newdb.DefaultIntegrationType.DiscordRole),
    ]
    if showanime.fsdb_data:
        if showanime.fsdb_data.id:
            integrations.append(
                newdb.IntegrationId(id=str(showanime.fsdb_data.id), type=newdb.DefaultIntegrationType.FansubDBProject),
            )
        if showanime.fsdb_data.ani_id:
            integrations.append(
                newdb.IntegrationId(
                    id=str(showanime.fsdb_data.ani_id), type=newdb.DefaultIntegrationType.FansubDBAnime
                ),
            )

    logger.info(f"   Processing {showanime.title}...")
    logger.info(f"   Processing {showanime.title} assigness...")
    actors = {}
    assignment, actors = await _process_showtimes_project_assignments(
        showanime.assignments,
        users,
        actors,
        session=session,
    )
    logger.info(f"   Processing {showanime.title} external Anilist data...")
    external_data = await _process_showtimes_project_external_data(showanime, session=session)
    logger.info(f"   Processing {showanime.title} new statuses format...")
    new_statuses = await _process_showtimes_project_episodes(showanime.status, assignment)

    last_update: DateTime = pendulum.now(tz="UTC")
    if showanime.last_update:
        try:
            last_update = pendulum.from_timestamp(showanime.last_update, tz="UTC")
        except Exception as exc:
            logger.warning(f"  Failed to parse last_update {showanime.last_update}, using current time instead")
            logger.exception(exc)

    ssproject = newdb.ShowProject(
        title=showanime.title,
        poster=ssposter,
        external=to_link(external_data),
        server_id=server_id,
        assignments=assignment,
        statuses=new_statuses,
        show_id=show_id,
        integrations=integrations,
        created_at=last_update,
        updated_at=last_update,
        aliases=showanime.aliases,
    )

    logger.info(f"   Adding {showanime.title}...")
    _ssproject = await newdb.ShowProject.insert_one(ssproject, session=session)
    if _ssproject is None:
        raise RuntimeError("Failed to add project")
    return _ssproject


async def _process_showtimes_server(
    showtimes: ShowtimesSchema, users: UsersHolder, *, session
) -> tuple[newdb.ShowtimesServer, UsersHolder, ProjectHolder]:
    integrations = [
        newdb.IntegrationId(id=str(showtimes.srv_id), type=newdb.DefaultIntegrationType.DiscordGuild),
    ]
    if showtimes.announce_channel:
        integrations.append(
            newdb.IntegrationId(
                id=str(showtimes.announce_channel),
                type=newdb.DefaultIntegrationType.PrefixAnnounce + newdb.DefaultIntegrationType.DiscordChannel,
            ),
        )
    if showtimes.fsdb_id:
        integrations.append(
            newdb.IntegrationId(
                id=str(showtimes.fsdb_id),
                type=newdb.DefaultIntegrationType.FansubDB,
            ),
        )

    owners_list: list[newdb.ShowtimesUserGroup] = []
    logger.info("  Processing owners...")
    session.start_transaction()
    for owner in showtimes.serverowner:
        if owner in users:
            owners_list.append(users[owner])
        else:
            ssuser = newdb.ShowtimesTemporaryUser(
                username=owner,
                password="unset_" + await encrypt_password(str(make_uuid())),
                type=newdb.ShowtimesTempUserType.MIGRATION,
            )
            _added_user = await newdb.ShowtimesTemporaryUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            users[owner] = _added_user
            owners_list.append(_added_user)
    await session.commit_transaction()

    sserver_id = make_uuid()

    SHOW_PROJECT: ProjectHolder = {}
    logger.info(f"  Processing {len(showtimes.anime)} projects...")
    for project in showtimes.anime:
        session.start_transaction()
        ssproject = await _process_showtimes_project(
            sserver_id,
            project,
            users,
            session=session,
        )
        SHOW_PROJECT[str(project.id)] = ssproject
        logger.info(f"   Committing project transaction {project.title}...")
        await session.commit_transaction()

    session.start_transaction()
    sserver = newdb.ShowtimesServer(
        name=showtimes.name or showtimes.srv_id,
        projects=[to_link(project) for project in SHOW_PROJECT.values()],
        integrations=integrations,
        owners=[to_link(owner) for owner in owners_list],
        server_id=sserver_id,
    )
    logger.info(f"  Adding server {sserver.name}...")
    _sserver_new = await newdb.ShowtimesServer.insert_one(sserver, session=session)
    if _sserver_new is None:
        raise RuntimeError("Failed to add server")
    logger.info(f" Committing to database... — {sserver.name}")
    await session.commit_transaction()

    return _sserver_new, users, SHOW_PROJECT


def _deduplicates_collaboration_data(data: CollabHolder) -> CollabHolder:
    # https://chat.openai.com/share/ec8b1f7c-1334-4599-a535-496075629e26
    # Might not cover some stupid edge cases, but it should be good enough
    # First pass: build the project_to_servers dictionary
    project_to_servers = {}

    for _, projects in data.items():
        for project in projects:
            project_id, collab_servers = project

            if project_id not in project_to_servers:
                project_to_servers[project_id] = set(collab_servers)
            else:
                project_to_servers[project_id] &= set(collab_servers)

    # Second pass: build the deduplicated data
    deduplicated_data: CollabHolder = {}
    seen_project_ids = set()
    for server_id, projects in data.items():
        for project in projects:
            project_id, collab_servers = project

            # Only keep a project if it hasn't been kept before and if the current server is in the list of servers
            # from the project_to_servers dictionary
            if project_id not in seen_project_ids and server_id in project_to_servers[project_id]:
                seen_project_ids.add(project_id)

                if server_id not in deduplicated_data:
                    deduplicated_data[server_id] = []

                deduplicated_data[server_id].append(project)

    return deduplicated_data


class Forward:
    @free_fall_migration(
        document_models=[
            newdb.ShowtimesServer,
            newdb.ShowProject,
            newdb.ShowtimesUser,
            newdb.ShowtimesTemporaryUser,
            newdb.ShowExternalData,
            newdb.ShowExternalTMDB,
            newdb.ShowExternalAnilist,
            newdb.RoleActor,
            newdb.ShowtimesCollaboration,
            newdb.ShowtimesCollaborationLinkSync,
            ShowtimesSchema,
            ShowAdminSchema,
            ShowtimesUISchema,
        ]
    )
    async def multi_migrate_schemas(self, session):
        env_config = get_env_config(include_environ=True)

        S3_ENDPOINT = env_config.get("S3_ENDPOINT")
        S3_KEY = env_config.get("S3_ACCESS_KEY")
        S3_SECRET = env_config.get("S3_SECRET_KEY")
        S3_REGION = env_config.get("S3_REGION")
        S3_BUCKET = env_config.get("S3_BUCKET")

        if S3_SECRET is not None and S3_KEY is not None and S3_BUCKET is not None:
            logger.info("Initializing S3 storage...")
            await init_s3_storage(S3_BUCKET, S3_KEY, S3_SECRET, S3_REGION, endpoint=S3_ENDPOINT)
            logger.info("S3 storage initialized!")

        logger.info("Creating Meilisearch client instances...")
        MEILI_URL = env_config.get("MEILI_URL")
        MEILI_API_KEY = env_config.get("MEILI_API_KEY")
        if MEILI_URL is None or MEILI_API_KEY is None:
            raise RuntimeError("No Meilisearch URL or API key specified")

        await init_searcher(MEILI_URL, MEILI_API_KEY)
        logger.info("Meilisearch client instances created!")
        meili_client = get_searcher()

        logger.info("Setting up Meilisearch indexes...")
        await meili_client.update_schema_settings(ProjectSearch)
        await meili_client.update_schema_settings(ServerSearch)
        await meili_client.update_schema_settings(UserSearch)

        logger.info("Fetching ShowtimesUISchema...")
        all_ui_info = await ShowtimesUISchema.find_all(session=session).to_list()
        logger.info("Fetching ShowAdminSchema...")
        all_owner_sets = await ShowAdminSchema.find_all(session=session).to_list()
        all_ui_ids = [ui.server_id for ui in all_ui_info]

        # Find intersects
        unregistered_ui: list[ShowAdminSchema] = []
        for owner in all_owner_sets:
            if owner.admin_id not in all_ui_ids:
                unregistered_ui.append(owner)

        # Migrate intersect
        ADDED_SHOWTIMES_USERS: UsersHolder = {}
        if unregistered_ui:
            logger.info(f"Found {len(unregistered_ui)} legacy users that are not registered, migrating...")
        SERVER_TO_USERS: dict[str, list[str]] = {}
        for missing_ui in unregistered_ui:
            ssuser = newdb.ShowtimesTemporaryUser(
                username=missing_ui.admin_id,
                password="unset_" + await encrypt_password(str(make_uuid())),
                type=newdb.ShowtimesTempUserType.MIGRATION,
                integrations=[
                    newdb.IntegrationId(id=str(missing_ui.admin_id), type=newdb.DefaultIntegrationType.DiscordUser)
                ],
            )
            _added_user = await newdb.ShowtimesTemporaryUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            ADDED_SHOWTIMES_USERS[missing_ui.admin_id] = _added_user
            for server in missing_ui.servers:
                if server not in SERVER_TO_USERS:
                    SERVER_TO_USERS[server] = []
                SERVER_TO_USERS[server].append(missing_ui.admin_id)
        logger.info(f"Found {len(all_ui_info)} legacy servers auth, migrating...")
        legacy_server_info: dict[str, ShowtimesUISchema] = {}
        for ui_info in all_ui_info:
            discord_meta: newdb.ShowtimesUserDiscord | None = None
            if ui_info.discord_meta:
                discord_meta = newdb.ShowtimesUserDiscord(
                    id=ui_info.discord_meta.id,
                    name=ui_info.discord_meta.name,
                    access_token=ui_info.discord_meta.access_token,
                    refresh_token=ui_info.discord_meta.refresh_token,
                    expires_at=ui_info.discord_meta.expires_at,
                )
            legacy_server_info[ui_info.server_id] = ui_info
            if discord_meta is None:
                continue
            password: str | None = None
            if ui_info.secret and ui_info.secret != "notset":  # noqa: S105
                password = await encrypt_password(ui_info.secret)
            ssuser = newdb.ShowtimesUser(
                username=discord_meta.id,
                privilege=ui_info.privilege.to_newdb(),
                password=password,
                name=ui_info.name,
                discord_meta=discord_meta,
                integrations=[
                    newdb.IntegrationId(id=str(discord_meta.id), type=newdb.DefaultIntegrationType.DiscordUser)
                ],
            )
            _added_user = await newdb.ShowtimesUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            ADDED_SHOWTIMES_USERS[ssuser.username] = _added_user

        logger.info("Trying to do extra legacy auth migration...")
        for server, users in SERVER_TO_USERS.items():
            if not users:
                continue
            logger.info(f"Found {len(users)} legacy users for server {server}, migrating...")
            ui_info = legacy_server_info.get(server)
            if ui_info is None:
                logger.warning(f"Could not find server info for {server}, skipping...")
                continue
            for user in users:
                first_user = ADDED_SHOWTIMES_USERS.get(user)
                if first_user is None:
                    continue
                if isinstance(first_user, newdb.ShowtimesUser):
                    if first_user.password is None:
                        # Set password
                        logger.info(f"Setting password for {first_user.username}...")
                        password = await encrypt_password(ui_info.secret)
                        first_user.password = password
                        await first_user.save(session=session)  # type: ignore
                        ADDED_SHOWTIMES_USERS[first_user.username] = first_user
                        break
                    continue
                elif isinstance(first_user, newdb.ShowtimesTemporaryUser):
                    # Migrate to full user
                    logger.info(f"Migrating {first_user.username} to full user...")
                    new_user = first_user.to_user(await encrypt_password(ui_info.secret), persist=True)
                    await first_user.delete(session=session)  # type: ignore
                    await newdb.ShowtimesUser.insert_one(new_user, session=session)
                    ADDED_SHOWTIMES_USERS[new_user.username] = new_user
                    break

        logger.info("Committing users transaction...")
        await session.commit_transaction()

        logger.info("Migrating ShowtimesSchema...")
        ADDED_SHOWTIMES_PROJECTS: dict[str, dict[str, newdb.ShowProject]] = {}
        ADDED_SHOWTIMES_SERVERS: dict[str, newdb.ShowtimesServer] = {}
        PENDING_CONFIRM: dict[str, list[ShowtimesCollabConfirmSchema]] = {}
        PENDING_COLLAB: CollabHolder = {}
        async for legacy_server in ShowtimesSchema.find_all(session=session):
            (
                added_server,
                ADDED_SHOWTIMES_USERS,
                projects,
            ) = await _process_showtimes_server(
                legacy_server,
                ADDED_SHOWTIMES_USERS,
                session=session,
            )

            ADDED_SHOWTIMES_PROJECTS.setdefault(legacy_server.srv_id, {}).update(projects)
            ADDED_SHOWTIMES_SERVERS[legacy_server.srv_id] = added_server
            PENDING_CONFIRM[legacy_server.srv_id] = legacy_server.konfirmasi

            for legacy_proj in legacy_server.anime:
                kolaborasi = [kolab for kolab in legacy_proj.kolaborasi if kolab != legacy_server.srv_id]
                if kolaborasi:
                    PENDING_COLLAB.setdefault(legacy_server.srv_id, []).append((legacy_proj.id, legacy_proj.kolaborasi))

        logger.info("Migrating ShowtimesCollabConfirmSchema...")
        session.start_transaction()
        for target_srv_id, src_pending in PENDING_CONFIRM.items():
            target_srv = ADDED_SHOWTIMES_SERVERS.get(target_srv_id)
            if target_srv is None:
                logger.warning(f"  Server {target_srv_id} not found, skipping...")
                continue

            for pending in src_pending:
                src_srv_info = ADDED_SHOWTIMES_SERVERS.get(pending.server_id)
                if src_srv_info is None:
                    logger.warning(f"  Server {pending.server_id} not found, skipping...")
                    continue
                src_proj_info = ADDED_SHOWTIMES_PROJECTS.get(pending.server_id, {}).get(pending.anime_id)
                if src_proj_info is None:
                    logger.warning(f"  Project {pending.anime_id} not found, skipping...")
                    continue
                target_proj_info = ADDED_SHOWTIMES_PROJECTS.get(target_srv_id, {}).get(pending.anime_id)

                sscollab = newdb.ShowtimesCollaboration(
                    code=pending.id,
                    source=newdb.ShowtimesCollaborationInfo(
                        server=to_link(src_srv_info),
                        project=to_link(src_proj_info),
                    ),
                    target=newdb.ShowtimesCollaborationInfo(
                        server=to_link(src_srv_info),
                        project=to_link(target_proj_info) if target_proj_info is not None else None,
                    ),
                )
                _sscollab = await newdb.ShowtimesCollaboration.insert_one(sscollab, session=session)
                if _sscollab is None:
                    raise RuntimeError("Failed to add collaboration")

        # Group up collabs, since each server and project would have their own collab info
        # We want to merge them together into one
        # dict[ServerId, list[tuple[ProjectId, list[CollabServerId]]]
        MERGED_COLLAB: CollabHolder = _deduplicates_collaboration_data(PENDING_COLLAB)
        logger.info("Migrating to ShowtimesCollaborationLinkSync...")
        for srv_id, collab_info in MERGED_COLLAB.items():
            _self_srv = ADDED_SHOWTIMES_SERVERS.get(srv_id)
            if _self_srv is None:
                logger.warning(f"  Base Server {srv_id} not found, skipping...")
                continue
            for proj_id, collab_srv_id in collab_info:
                collab_srv: list[tuple[ServerId, UUID]] = [
                    (srv_id, _self_srv.server_id),
                ]

                for srv in collab_srv_id:
                    if srv == srv_id:
                        continue
                    _srv = ADDED_SHOWTIMES_SERVERS.get(srv)
                    if _srv is None:
                        logger.warning(f"  Some servers in {collab_srv_id} not found!")
                        continue

                    collab_srv.append((srv, _srv.server_id))

                all_proj_info: list[UUID] = []
                skip_server = []
                for ssid, _ in collab_srv:
                    proj_d = ADDED_SHOWTIMES_PROJECTS.get(ssid, {}).get(proj_id)
                    if proj_d is None:
                        logger.warning(f"  Project {proj_id} not found in {ssid}!")
                        skip_server.append(ssid)
                        continue
                    all_proj_info.append(proj_d.show_id)

                if not all_proj_info:
                    logger.warning(f"  No project found for {proj_id}!")
                    continue

                collab_srv = [(ssid, proj_id) for ssid, proj_id in collab_srv if ssid not in skip_server]
                if not collab_srv:
                    logger.warning(f"  No server found for {proj_id}!")
                    continue

                collab_srv_id = [proj_id for _, proj_id in collab_srv]

                collab_link = newdb.ShowtimesCollaborationLinkSync(
                    projects=all_proj_info,
                    servers=collab_srv_id,
                )
                _cres = await newdb.ShowtimesCollaborationLinkSync.insert_one(collab_link, session=session)
                if _cres is None:
                    raise RuntimeError("Failed to add collaboration link")

        logger.info("Committing collaboration data...")
        await session.commit_transaction()

        logger.info("Creating Meilisearch index...")
        search_srv_docs: list[ServerSearch] = []
        for server in ADDED_SHOWTIMES_SERVERS.values():
            search_srv_docs.append(ServerSearch.from_db(server))
        logger.info(f"  Adding {len(search_srv_docs)} documents to Server Index...")
        await meili_client.add_documents(search_srv_docs)
        search_proj_docs: list[ProjectSearch] = []
        for projects in ADDED_SHOWTIMES_PROJECTS.values():
            for project in projects.values():
                search_proj_docs.append(ProjectSearch.from_db(project))
        logger.info(f"  Adding {len(search_proj_docs)} documents to Project Index...")
        await meili_client.add_documents(search_proj_docs)
        search_user_docs: list[UserSearch] = []
        for user in ADDED_SHOWTIMES_USERS.values():
            search_user_docs.append(UserSearch.from_db(user))
        logger.info(f"  Adding {len(search_user_docs)} documents to User Index...")
        await meili_client.add_documents(search_user_docs)

        logger.info("Closing Meilisearch client instances...")
        await meili_client.close()
        logger.info("Closed Meilisearch client instances!")

        try:
            s3_bucket = get_s3_storage()
            logger.info("Closing S3 storage...")
            await s3_bucket.close()
        except Exception as exc:
            logger.exception(exc)
            logger.warning("Failed to close S3 storage")


class Backward:
    @free_fall_migration(
        document_models=[
            newdb.ShowtimesServer,
            newdb.ShowProject,
            newdb.ShowtimesUser,
            newdb.ShowtimesTemporaryUser,
            newdb.ShowExternalData,
            newdb.ShowExternalTMDB,
            newdb.ShowExternalAnilist,
            newdb.RoleActor,
            newdb.ShowtimesCollaboration,
            newdb.ShowtimesCollaborationLinkSync,
        ]
    )
    async def revert_by_delete(self, session):
        # Cascade delete
        env_config = get_env_config(include_environ=True)

        S3_ENDPOINT = env_config.get("S3_ENDPOINT")
        S3_KEY = env_config.get("S3_ACCESS_KEY")
        S3_SECRET = env_config.get("S3_SECRET_KEY")
        S3_REGION = env_config.get("S3_REGION")
        S3_BUCKET = env_config.get("S3_BUCKET")

        if S3_SECRET is not None and S3_KEY is not None and S3_BUCKET is not None:
            logger.info("Initializing S3 storage...")
            await init_s3_storage(S3_BUCKET, S3_KEY, S3_SECRET, S3_REGION, endpoint=S3_ENDPOINT)
            logger.info("S3 storage initialized!")

        logger.info("Creating Meilisearch client instances...")
        MEILI_URL = env_config.get("MEILI_URL")
        MEILI_API_KEY = env_config.get("MEILI_API_KEY")
        if MEILI_URL is None or MEILI_API_KEY is None:
            raise RuntimeError("No Meilisearch URL or API key specified")

        await init_searcher(MEILI_URL, MEILI_API_KEY)
        logger.info("Meilisearch client instances created!")
        meili_client = get_searcher()

        logger.info("Deleting ShowtimesUser...")
        await newdb.ShowtimesUser.delete_all(session=session)
        logger.info("Deleting ShowtimesTemporaryUser...")
        await newdb.ShowtimesTemporaryUser.delete_all(session=session)
        logger.info("Deleting ShowtimesServer...")
        await newdb.ShowtimesServer.delete_all(session=session)
        logger.info("Deleting ShowProject...")
        show_projects = await newdb.ShowProject.find_all(session=session).to_list()
        storage = get_storage()
        for show_project in show_projects:
            poster = show_project.poster.image
            try:
                logger.info(f"  Deleting poster {poster.key}...")
                await storage.delete(poster.key, poster.parent, poster.filename, type="project")
            except Exception as exc:
                logger.exception(exc)
                logger.warning(f"  Failed to delete poster {poster.key}")
        await newdb.ShowProject.delete_all(session=session)
        logger.info("Deleting ShowExternalData...")
        await newdb.ShowExternalAnilist.delete_all(session=session)
        await newdb.ShowExternalTMDB.delete_all(session=session)
        await newdb.ShowExternalData.delete_all(session=session)
        logger.info("Deleting RoleActor...")
        await newdb.RoleActor.delete_all(session=session)
        logger.info("Deleting ShowtimesCollaboration...")
        await newdb.ShowtimesCollaboration.delete_all(session=session)
        logger.info("Deleting ShowtimesCollaborationLinkSync...")
        await newdb.ShowtimesCollaborationLinkSync.delete_all(session=session)
        logger.info("Rolled back everything!")

        await meili_client.delete_index(ProjectSearch.Config.index)
        await meili_client.delete_index(ServerSearch.Config.index)
        await meili_client.delete_index(UserSearch.Config.index)

        try:
            s3_bucket = get_s3_storage()
            logger.info("Closing S3 storage...")
            await s3_bucket.close()
        except Exception as exc:
            logger.exception(exc)
            logger.warning("Failed to close S3 storage")
