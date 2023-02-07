from enum import Enum
from typing import Any, cast

from beanie import Document, Link, free_fall_migration
import pendulum
from pydantic import BaseModel, Field

from showtimes.models import database as newdb
from showtimes.security import encrypt_password


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
        fields = {"srv_id": "id", "id": "_id"}


class ShowAdminSchema(Document):
    admin_id: str
    # Bind the _id to mongo_id
    servers: list[str] = Field(default_factory=list)

    class Settings:
        name = "showtimesadmin"

    class Config:
        fields = {"admin_id": "id", "id": "_id"}


class ShowUIPrivilege(str, Enum):
    ADMIN = "owner"
    SERVER = "server"


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

    class Settings:
        name = "showtimesuilogin"

    class Config:
        fields = {"user_id": "id", "id": "_id"}


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


def find_integration(integrations: list[newdb.IntegrationId], id: str, type: str) -> newdb.IntegrationId | None:
    for integration in integrations:
        if integration.id == id and integration.type == type:
            return integration


def collect_integration(integrations: list[newdb.IntegrationId], type: str) -> list[newdb.IntegrationId]:
    return list(filter(lambda x: x.type == type, integrations))


class Forward:
    def _sel_actor(self, actor: newdb.RoleActor, assignee: ShowAnimeAssigneeSchema) -> tuple[newdb.RoleActor, bool]:
        id = cast(str, assignee.id)
        if find_integration(actor.integrations, id, newdb.DefaultIntegrationType.DiscordUser) is None:
            # Let's create a new actor
            sel_actor = newdb.RoleActor(
                name=assignee.name or "",
                avatar="",
                integrations=[
                    newdb.IntegrationId(
                        id=id,
                        type=newdb.DefaultIntegrationType.DiscordUser,
                    )
                ],
            )
            bb = True
        else:
            sel_actor = actor
            bb = False
        return sel_actor, bb

    def _get_actor(self, actors: list[newdb.RoleActor], id: str):
        for actor in actors:
            if (
                find_integration(actor.integrations, cast(str, id), newdb.DefaultIntegrationType.DiscordUser)
                is not None
            ):
                return actor

    def _create_show_actors(self, assignments: ShowAnimeAssignmentsSchema, existing_actors: list[newdb.RoleActor]):
        new_actors: list[newdb.RoleActor] = []

        tl = assignments.TL
        tlc = assignments.TLC
        enc = assignments.ENC
        ed = assignments.ED
        tm = assignments.TM
        ts = assignments.TS
        qc = assignments.QC
        custom = assignments.custom

        show_actors: list[newdb.ShowActor] = []
        marked_actors: list[str] = []
        for actor in existing_actors:
            if tl.id is not None and "TL" not in marked_actors:
                sel_act, push = self._sel_actor(actor, tl)
                if (tt := self._get_actor(new_actors, tl.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="TL", actor=sel_act),  # type: ignore
                )
                marked_actors.append("TL")
            if tlc.id is not None and "TLC" not in marked_actors:
                sel_act, push = self._sel_actor(actor, tlc)
                if (tt := self._get_actor(new_actors, tlc.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="TLC", actor=sel_act),  # type: ignore
                )
                marked_actors.append("TLC")
            if ed.id is not None and "ED" not in marked_actors:
                sel_act, push = self._sel_actor(actor, ed)
                if (tt := self._get_actor(new_actors, ed.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="ED", actor=sel_act),  # type: ignore
                )
                marked_actors.append("ED")
            if enc.id is not None and "ENC" not in marked_actors:
                sel_act, push = self._sel_actor(actor, enc)
                if (tt := self._get_actor(new_actors, enc.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="ENC", actor=sel_act),  # type: ignore
                )
                marked_actors.append("ENC")
            if tm.id is not None and "TM" not in marked_actors:
                sel_act, push = self._sel_actor(actor, tm)
                if (tt := self._get_actor(new_actors, tm.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="TM", actor=sel_act),  # type: ignore
                )
                marked_actors.append("TM")
            if ts.id is not None and "TS" not in marked_actors:
                sel_act, push = self._sel_actor(actor, ts)
                if (tt := self._get_actor(new_actors, ts.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="TS", actor=sel_act),  # type: ignore
                )
                marked_actors.append("TS")
            if qc.id is not None and "QC" not in marked_actors:
                sel_act, push = self._sel_actor(actor, qc)
                if (tt := self._get_actor(new_actors, qc.id)) is not None:
                    push = False
                    sel_act = tt
                if push:
                    new_actors.append(sel_act)
                show_actors.append(
                    newdb.ShowActor(key="QC", actor=sel_act),  # type: ignore
                )
                marked_actors.append("QC")
            for cust in custom:
                person = cust.person
                if person.id is not None and cust.key not in marked_actors:
                    sel_act, push = self._sel_actor(actor, person)
                    if (tt := self._get_actor(new_actors, person.id)) is not None:
                        push = False
                        sel_act = tt
                    if push:
                        new_actors.append(sel_act)
                    show_actors.append(
                        newdb.ShowActor(key=cust.key, actor=sel_act),  # type: ignore
                    )
                    marked_actors.append(cust.key)
        return show_actors, new_actors

    def _create_new_episode_fmt(self, old_episodes: list[EpisodeStatusSchema]):
        new_episodes: list[newdb.EpisodeStatus] = []
        print("    ∟ Creating new episode format...")
        for status in old_episodes:
            role_statuses: list[newdb.RoleStatus] = []
            role_statuses.extend(
                [
                    newdb.RoleStatus(key="TL", name="Translator", finished=status.progress.TL),
                    newdb.RoleStatus(key="TLC", name="Translation Checker", finished=status.progress.TLC),
                    newdb.RoleStatus(key="ENC", name="Encoder", finished=status.progress.ENC),
                    newdb.RoleStatus(key="ED", name="Editor", finished=status.progress.ED),
                    newdb.RoleStatus(key="TS", name="Typesetter", finished=status.progress.TS),
                    newdb.RoleStatus(key="TM", name="Timer", finished=status.progress.TM),
                    newdb.RoleStatus(key="QC", name="Quality Checker", finished=status.progress.QC),
                ]
            )
            for stat_cust in status.progress.custom:
                role_statuses.append(newdb.RoleStatus(key=stat_cust.key, name=stat_cust.name, finished=stat_cust.done))
            episode = newdb.EpisodeStatus(
                episode=status.episode,
                is_released=status.is_done,
                airing_at=status.airtime,
                statuses=role_statuses,
                delay_reason=status.delay_reason,
            )
            new_episodes.append(episode)
        return new_episodes

    def _create_external_data(self, project: ShowAnimeSchema):
        episode_data: list[newdb.ShowExternalEpisode] = []
        for status in project.status:
            episode_data.append(newdb.ShowExternalEpisode(episode=status.episode, airtime=status.airtime))
        return newdb.ShowExternalAnilist(
            episodes=episode_data,
            ani_id=str(project.id),
            mal_id=str_or_none(project.mal_id),
            start_time=int_or_none(project.start_time),
        )

    async def _create_new_server_data(
        self, old_srv: ShowtimesSchema, server_to_owner: dict[str, list[str]], created_actors: list[newdb.RoleActor]
    ):
        print(f"  ∟ Creating new server data for {old_srv.srv_id}")
        # Initial data
        integrations_db: list[newdb.IntegrationId] = []
        if old_srv.announce_channel is not None:
            integrations_db.append(
                newdb.IntegrationId(id=old_srv.announce_channel, type=newdb.DefaultIntegrationType.DiscordChannel)
            )
        if old_srv.fsdb_id is not None:
            integrations_db.append(
                newdb.IntegrationId(id=str(old_srv.fsdb_id), type=newdb.DefaultIntegrationType.FansubDB)
            )
        srv_actors: list[Link[newdb.RoleActor]] = []
        current_actors_list = created_actors[:]
        for owner in old_srv.serverowner:
            actor = self._get_actor(current_actors_list, owner)
            if actor is None:
                # Craete new actor
                actor = newdb.RoleActor(
                    name="",
                    avatar="",
                    integrations=[newdb.IntegrationId(id=str(owner), type=newdb.DefaultIntegrationType.DiscordUser)],
                )
                await actor.save()
                current_actors_list.append(actor)
            srv_actors.append(newdb.RoleActor.link_from_id(actor.id))
        new_srv = newdb.ShowtimesServer(
            name=old_srv.name or old_srv.srv_id,
            integrations=integrations_db,
            # TODO: fix this
            # owners=srv_actors,
        )
        await new_srv.save()
        new_projects: list[Link[newdb.ShowProject]] = []
        collaborations_hell = []
        for project in old_srv.anime:
            print(f"    ∟ Creating new project data for {project.title}")
            anilist_data = self._create_external_data(project)
            show_actors, new_actors = self._create_show_actors(project.assignments, current_actors_list)
            await anilist_data.save()
            print(f"    ∟ Committing {len(new_actors)} new actors")
            for actor in new_actors:
                current_actors_list.append(actor)
                await actor.save()
            last_update = pendulum.from_timestamp(project.last_update)
            integrations: list[newdb.IntegrationId] = []
            if project.role_id is not None:
                integrations.append(
                    newdb.IntegrationId(
                        id=project.role_id,
                        type=newdb.DefaultIntegrationType.DiscordRole,
                    )
                )
            if project.fsdb_data is not None:
                if (fspj_id := project.fsdb_data.id) is not None:
                    integrations.append(
                        newdb.IntegrationId(
                            id=str(fspj_id),
                            type=newdb.DefaultIntegrationType.FansubDBProject,
                        )
                    )
                    if (fsani_id := project.fsdb_data.ani_id) is not None:
                        integrations.append(
                            newdb.IntegrationId(
                                id=str(fsani_id),
                                type=newdb.DefaultIntegrationType.FansubDBAnime,
                            )
                        )
            for _ in collaborations_hell:
                pass
            new_project = newdb.ShowProject(
                title=project.title,
                poster=newdb.ShowPoster(url=project.poster_data.url, color=int_or_none(project.poster_data.color)),
                external=newdb.ShowExternalAnilist.link_from_id(anilist_data.id),  # type: ignore
                assignments=show_actors,
                episodes=self._create_new_episode_fmt(project.status),
                created_at=last_update,
                updated_at=last_update,
                integrations=integrations,
            )
            await new_project.save()
            new_projects.append(newdb.ShowProject.link_from_id(new_project.id))
        new_srv.projects = new_projects
        await new_srv.save()

    @free_fall_migration(
        document_models=[
            newdb.ShowtimesServer,
            newdb.ShowProject,
            newdb.ShowtimesUser,
            newdb.ShowExternalData,
            newdb.RoleActor,
            ShowtimesSchema,
            ShowAdminSchema,
            ShowtimesUISchema,
        ]
    )
    async def multi_migrate_schemas(self, session):
        # Get all admin IDs
        print("Initializing server migration")
        server_to_owner: dict[str, list[str]] = {}
        print("Server to admin mapping...", end="\r")
        created_actors: list[newdb.RoleActor] = []
        async for admin in ShowAdminSchema.find_all(session=session):
            for server in admin.servers:
                server_to_owner.setdefault(server, []).append(admin.admin_id)
        print("Server to admin mapping... done")
        print("Creating showtimes users...", end="\r")
        showtimes_users = []
        async for user in ShowtimesUISchema.find_all(session=session):
            passwd = await encrypt_password(user.secret)
            disc_meta = None  # type: newdb.ShowtimesUserDiscord | None
            if user.discord_meta is not None:
                disc_meta = newdb.ShowtimesUserDiscord(
                    id=user.discord_meta.id,
                    name=user.discord_meta.name,
                    access_token=user.discord_meta.access_token,
                    refresh_token=user.discord_meta.refresh_token,
                    expires_at=user.discord_meta.expires_at,
                )
            ssuser = newdb.ShowtimesUser(
                username=user.user_id,
                password=passwd,
                privilege=newdb.UserType.ADMIN if user.privilege is ShowUIPrivilege.ADMIN else newdb.UserType.USER,
                discord_meta=disc_meta,
            )
            await ssuser.save(session=session)
            showtimes_users.append(ssuser)
        print("Creating role actors...", end="\r")
        for owners in server_to_owner.values():
            for owner in owners:
                actor = newdb.RoleActor(
                    name="",
                    avatar="",
                    integrations=[newdb.IntegrationId(id=owner, type=newdb.DefaultIntegrationType.DiscordUser)],
                )
                await actor.save(session=session)
                created_actors.append(actor)
        print("Creating role actors... done")
        print("Migrating servers...", end="\r")
        async for server in ShowtimesSchema.find_all(session=session):
            await self._create_new_server_data(server, server_to_owner, created_actors)


class Backward:  # no backward implementation, so we can't rollback
    ...
