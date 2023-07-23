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

import aiohttp
import pendulum
from beanie import Document, Link, free_fall_migration
from pendulum.datetime import DateTime
from pydantic import BaseModel, Field

from showtimes.controllers.security import encrypt_password
from showtimes.controllers.storages import get_storage, init_s3_storage
from showtimes.models import database as newdb
from showtimes.tooling import get_env_config, setup_logger
from showtimes.utils import make_uuid, try_int

CURRENT_DIR = Path(__file__).absolute().parent
ROOT_DIR = CURRENT_DIR.parent
logger = setup_logger(ROOT_DIR / "logs" / "migrations")


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
    user_id: str
    secret: str
    name: str | None = Field(default=None)
    privilege: ShowUIPrivilege = Field(default=ShowUIPrivilege.SERVER)
    discord_meta: ShowUIDiscordMeta | None = Field(default=None)
    user_type: ShowUIUserType = Field(default=ShowUIUserType.SERVER)

    class Settings:
        name = "showtimesuilogin"

    class Config:
        fields: dict[str, str] = {"user_id": "id", "id": "_id"}  # noqa: RUF012


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
UsersHolder: TypeAlias = dict[str, newdb.ShowtimesUser]
RolesHolder: TypeAlias = dict[str, newdb.RoleActor]
ProjectHolder: TypeAlias = dict[ProjectId, newdb.ShowProject]
CollabHolder: TypeAlias = dict[ServerId, list[tuple[ProjectId, list[ServerId]]]]
DocT = TypeVar("DocT", bound=Document)


def to_link(doc: DocT) -> Link[DocT]:
    dbref = doc.to_ref()
    return Link(ref=dbref, model_class=doc.__class__)


async def _upload_poster(server_id: str, project_id: str, poster: ShowAnimePosterSchema):
    stor = get_storage()

    async with aiohttp.ClientSession() as session:
        async with session.get(poster.url) as resp:
            resp.raise_for_status()

            bytes_data = await resp.read()

    poster_ext = Path(poster.url).suffix
    bytes_io = BytesIO(bytes_data)
    bytes_io.seek(0)
    logger.info(f"  Uploading poster{poster_ext}...")
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
            filename=f"poster{poster_ext}",
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
) -> tuple[newdb.RoleActor | None, RolesHolder]:
    if assigned_id is None:
        return None, actors

    if not is_valid_snowflake(assigned_id):
        return None, actors

    if assigned_id in actors:
        return actors[assigned_id], actors

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
    return _new_actor, actors


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
    if TLActor:
        show_actors.append(newdb.ShowActor(actor=to_link(TLActor), key="TL"))
    if TLCActor:
        show_actors.append(newdb.ShowActor(actor=to_link(TLCActor), key="TLC"))
    if ENCActor:
        show_actors.append(newdb.ShowActor(actor=to_link(ENCActor), key="ENC"))
    if EDActor:
        show_actors.append(newdb.ShowActor(actor=to_link(EDActor), key="ED"))
    if TSActor:
        show_actors.append(newdb.ShowActor(actor=to_link(TSActor), key="TS"))
    if TMActor:
        show_actors.append(newdb.ShowActor(actor=to_link(TMActor), key="TM"))
    if QCActor:
        show_actors.append(newdb.ShowActor(actor=to_link(QCActor), key="QC"))
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
        if custom_actor:
            show_actors.append(newdb.ShowActor(actor=to_link(custom_actor), key=custom.key))
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
        episode_data.append(
            newdb.ShowExternalEpisode(
                episode=status.episode,
                airtime=status.airtime,
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
    server_id: UUID, showanime: ShowAnimeSchema, users: UsersHolder, actors: RolesHolder, *, session
) -> tuple[newdb.ShowProject, RolesHolder]:
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

    assignment, actors = await _process_showtimes_project_assignments(
        showanime.assignments,
        users,
        actors,
        session=session,
    )
    external_data = await _process_showtimes_project_external_data(showanime, session=session)
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
    )

    _ssproject = await newdb.ShowProject.insert_one(ssproject, session=session)
    if _ssproject is None:
        raise RuntimeError("Failed to add project")
    return _ssproject, actors


async def _process_showtimes_server(
    showtimes: ShowtimesSchema, users: UsersHolder, actors: RolesHolder, *, session
) -> tuple[newdb.ShowtimesServer, UsersHolder, RolesHolder, ProjectHolder]:
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

    owners_list: list[newdb.ShowtimesUser] = []
    for owner in showtimes.serverowner:
        if owner in users:
            owners_list.append(users[owner])
        else:
            ssuser = newdb.ShowtimesUser(
                username=owner,
                privilege=newdb.UserType.USER,
            )
            _added_user = await newdb.ShowtimesUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            users[owner] = _added_user
            owners_list.append(_added_user)

    sserver_id = make_uuid()

    SHOW_PROJECT: ProjectHolder = {}
    for project in showtimes.anime:
        ssproject, actors = await _process_showtimes_project(
            sserver_id,
            project,
            users,
            actors,
            session=session,
        )
        SHOW_PROJECT[str(project.id)] = ssproject

    sserver = newdb.ShowtimesServer(
        name=showtimes.name or showtimes.srv_id,
        projects=[to_link(project) for project in SHOW_PROJECT.values()],
        integrations=integrations,
        owners=[to_link(owner) for owner in owners_list],
        server_id=sserver_id,
    )
    _sserver_new = await newdb.ShowtimesServer.insert_one(sserver, session=session)
    if _sserver_new is None:
        raise RuntimeError("Failed to add server")

    return _sserver_new, users, actors, SHOW_PROJECT


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
            newdb.ShowExternalData,
            newdb.ShowExternalTMDB,
            newdb.ShowExternalAnilist,
            newdb.RoleActor,
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

        logger.info("Fetching ShowtimesUISchema...")
        all_ui_info = await ShowtimesUISchema.find_all(session=session).to_list()
        logger.info("Fetching ShowAdminSchema...")
        all_owner_sets = await ShowAdminSchema.find_all(session=session).to_list()
        all_ui_ids = [ui.user_id for ui in all_ui_info]

        # Find intersects
        unregistered_ui: list[ShowAdminSchema] = []
        for owner in all_owner_sets:
            if owner.admin_id not in all_ui_ids:
                unregistered_ui.append(owner)

        # Migrate intersect
        logger.info(f"Found {len(all_ui_info)} legacy users, migrating...")
        ADDED_SHOWTIMES_USERS: UsersHolder = {}
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
            password = None
            if ui_info.user_type == ShowUIUserType.SERVER:
                password = await encrypt_password(ui_info.secret)
            ssuser = newdb.ShowtimesUser(
                username=ui_info.user_id,
                privilege=ui_info.privilege.to_newdb(),
                password=password,
                name=ui_info.name,
                discord_meta=discord_meta,
            )
            _added_user = await newdb.ShowtimesUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            ADDED_SHOWTIMES_USERS[ui_info.user_id] = _added_user
        if unregistered_ui:
            logger.info(f"Found {len(unregistered_ui)} legacy users that are not registered, migrating...")
        for missing_ui in unregistered_ui:
            ssuser = newdb.ShowtimesUser(
                username=missing_ui.admin_id,
                privilege=newdb.UserType.USER,
            )
            _added_user = await newdb.ShowtimesUser.insert_one(ssuser, session=session)
            if _added_user is None:
                raise RuntimeError("Failed to add user")
            ADDED_SHOWTIMES_USERS[missing_ui.admin_id] = _added_user

        ADDED_ROLE_ACTORS: RolesHolder = {}
        logger.info(f"Creating default {len(ADDED_SHOWTIMES_USERS)} role actors from migrated users...")
        for ssuser in ADDED_SHOWTIMES_USERS.values():
            roleact = newdb.RoleActor(
                name=ssuser.name or ssuser.username,
                integrations=[
                    newdb.IntegrationId(id=str(ssuser.user_id), type=newdb.DefaultIntegrationType.ShowtimesUser),
                    newdb.IntegrationId(id=str(ssuser.username), type=newdb.DefaultIntegrationType.DiscordUser),
                ],
            )
            _added_roleact = await newdb.RoleActor.insert_one(roleact, session=session)
            if _added_roleact is None:
                raise RuntimeError("Failed to add role actor")
            ADDED_ROLE_ACTORS[ssuser.username] = _added_roleact

        logger.info("Migrating ShowtimesSchema...")
        ADDED_SHOWTIMES_PROJECTS: dict[str, dict[str, newdb.ShowProject]] = {}
        ADDED_SHOWTIMES_SERVERS: dict[str, newdb.ShowtimesServer] = {}
        PENDING_CONFIRM: dict[str, list[ShowtimesCollabConfirmSchema]] = {}
        PENDING_COLLAB: CollabHolder = {}
        async for legacy_server in ShowtimesSchema.find_all(session=session):
            (
                added_server,
                ADDED_SHOWTIMES_USERS,
                ADDED_ROLE_ACTORS,
                projects,
            ) = await _process_showtimes_server(
                legacy_server,
                ADDED_SHOWTIMES_USERS,
                ADDED_ROLE_ACTORS,
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
                proj_info = ADDED_SHOWTIMES_PROJECTS.get(pending.server_id, {}).get(pending.anime_id)
                if proj_info is None:
                    logger.warning(f"  Project {pending.anime_id} not found, skipping...")
                    continue

                sscollab = newdb.ShowtimesCollaboration(
                    code=pending.id,
                    source=to_link(src_srv_info),
                    target=to_link(target_srv),
                    project=to_link(proj_info),
                )
                _sscollab = await newdb.ShowtimesCollaboration.insert_one(sscollab, session=session)
                if _sscollab is None:
                    raise RuntimeError("Failed to add collaboration")

        # Group up collabs, since each server and project would have their own collab info
        # We want to merge them together into one
        # dict[ServerId, list[tuple[ProjectId, list[CollabServerId]]]
        MERGED_COLLAB: CollabHolder = _deduplicates_collaboration_data(PENDING_COLLAB)
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


class Backward:  # no backward implementation, so we can't rollback
    ...
