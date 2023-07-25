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
from typing import Optional, TypeVar
from uuid import UUID

from beanie import (
    Document,
    Insert,
    Link,
    Replace,
    Save,
    SaveChanges,
    Update,
    ValidateOnSave,
    after_event,
    before_event,
)
from pendulum.datetime import DateTime
from pydantic import BaseModel, Field

from ..utils import generate_custom_code, make_uuid
from ._doc import _coerce_to_pendulum, pendulum_utc

AllEvent = [Insert, Replace, Update, Save, SaveChanges, ValidateOnSave]
DocT = TypeVar("DocT", bound=Document)


def to_link(doc: DocT) -> Link[DocT]:
    dbref = doc.to_ref()
    return Link(ref=dbref, model_class=doc.__class__)


class ImageMetadata(BaseModel):
    """
    The user avatar image.
    """

    type: str
    """The type of the image"""
    key: str
    """The key of the image"""
    parent: str | None
    """The parent of the image, if any."""
    filename: str
    """The filename of the image"""
    format: str = ""
    """The format of the image"""

    def as_url(self):
        if self.parent is None:
            return f"/{self.type}/{self.key}/{self.filename}"
        return f"/{self.type}/{self.key}/{self.parent}/{self.filename}"


class DefaultIntegrationType:
    """
    A simple class to hold the default integration type.
    """

    DiscordRole = "DISCORD_ROLE"
    DiscordUser = "DISCORD_USER"
    DiscordChannel = "DISCORD_TEXT_CHANNEL"
    DiscordGuild = "DISCORD_GUILD"
    FansubDB = "FANSUBDB_ID"
    FansubDBProject = "FANSUBDB_PROJECT_ID"
    FansubDBAnime = "FANSUBDB_ANIME_ID"
    ShowtimesUser = "SHOWTIMES_USER"
    PrefixAnnounce = "ANNOUNCEMENT_"


class IntegrationId(BaseModel):
    """
    Model to hold the ID of an integration.

    This can be used to denote Discord Integration
    like which actor is linked to which Discord user.
    """

    id: str
    type: str  # Example: discord, telegram, etc.
    # A more complex example would be:
    # - DISCORD_ROLE: The role ID of the role.
    # - DISCORD_USER: The user ID of the user.

    @before_event(Insert, Replace, Update, SaveChanges)
    def capitalize_type(self):
        self.type = self.type.upper()


class RoleStatus(BaseModel):
    """
    The model to hold each role status.
    This will be linked to the actor/assignment later.

    Each `key` should be unique and capitalized.
    Name is the long name in any language you want.
    Finished will be used to denote if the role has finished
    their job or not.
    """

    key: str
    name: str
    """
    The expanded name of the key.
    Developer can also implement their own translation as long,
    as it is mapped to the key on their program.

    Some default key are:
    - TL
    - TLC
    - ENC
    - ED
    - TM
    - TS
    - QC
    """
    finished: bool = Field(default=False)


class RoleActor(Document):
    """
    The actor model, only exists once per actor.
    """

    name: str
    integrations: list[IntegrationId] = Field(default_factory=list)
    actor_id: UUID = Field(default_factory=make_uuid)

    class Settings:
        name = "ShowtimesActors"
        use_state_management = True


# Default roles for each show.
DEFAULT_ROLES_SHOWS = [
    RoleStatus(key="TL", name="Translator"),
    RoleStatus(key="TLC", name="Translation Checker"),
    RoleStatus(key="ENC", name="Encoder"),
    RoleStatus(key="ED", name="Editor"),
    RoleStatus(key="TS", name="Typesetter"),
    RoleStatus(key="TM", name="Timer"),
    RoleStatus(key="QC", name="Quality Checker"),
]
DEFAULT_ROLES_MANGA = [
    RoleStatus(key="TL", name="Translator"),
    RoleStatus(key="CL", name="Cleaner"),
    RoleStatus(key="RD", name="Redrawer"),
    RoleStatus(key="PR", name="Proofreader"),
    RoleStatus(key="TS", name="Typesetter"),
    RoleStatus(key="QC", name="Quality Checker"),
]
DEFAULT_ROLES_NOVEL = [
    RoleStatus(key="TL", name="Translator"),
    RoleStatus(key="TLC", name="Translation Checker"),
    RoleStatus(key="ED", name="Editor"),
    RoleStatus(key="PR", name="Proofreader"),
    RoleStatus(key="QC", name="Quality Checker"),
]


class EpisodeStatus(BaseModel):
    """
    The model to hold each episode status.
    """

    episode: int
    """Episode number"""
    is_released: bool
    """Has the episode released?"""
    airing_at: Optional[float] = None
    """The unix timestamp of the airing time, if any."""
    statuses: list[RoleStatus] = Field(default_factory=lambda: DEFAULT_ROLES_SHOWS)
    """The statuses of each role."""
    delay_reason: Optional[str] = None
    """The reason for the delay, if any."""


class ShowActor(BaseModel):
    """
    The model to hold the actor/asignee of each role.

    key should exist in the status model.
    actor is the link to the actor model, can be reused obviously.
    """

    key: str
    """The key name of the actor. (should be uppercase)"""
    actor: Optional[Link[RoleActor]] = None
    """The link to the actor model."""


class ShowPoster(BaseModel):
    image: ImageMetadata
    """The URL to the poster."""
    color: Optional[int] = None
    """The int color of the poster, representation only."""


class ShowExternalType(str, Enum):
    ANILIST = "ANILIST"
    TMDB = "THEMOVIEDB"

    UNKNOWN = "INVALID_EXTERNAL_TYPE"


class ShowExternalEpisode(BaseModel):
    episode: int
    airtime: float
    season: int = Field(default=1)
    title: Optional[str] = None
    """The unix timestamp of the airing time, if any."""


class ShowExternalData(Document):
    episodes: list[ShowExternalEpisode] = Field(default_factory=list)
    type: ShowExternalType = ShowExternalType.UNKNOWN

    class Settings:
        name = "ShowtimesExternals"
        is_root = True
        use_state_management = True


class ShowExternalStart(BaseModel):
    """Start time mixin for external data."""

    start_time: Optional[float] = None


class ShowExternalAnilist(ShowExternalData, ShowExternalStart):
    ani_id: str
    mal_id: Optional[str] = None  # for other integration

    @before_event(Insert, Replace, Update, SaveChanges)
    def force_type(self):
        # DO NOT ALLOW THIS TO BE CHANGED.
        self.type = ShowExternalType.ANILIST


class ShowExternalTMDB(ShowExternalData, ShowExternalStart):
    tmdb_id: str

    @before_event(Insert, Replace, Update, SaveChanges)
    def force_type(self):
        # DO NOT ALLOW THIS TO BE CHANGED.
        self.type = ShowExternalType.TMDB


class ShowProject(Document):
    """
    The document to hold each project.
    """

    title: str
    """The title of the project"""
    poster: ShowPoster
    """The poster/cover of the project"""
    external: Link[ShowExternalData]
    """The external data of the project, linked to the external document."""
    server_id: UUID
    """The ID of the server that owns this project."""

    assignments: list[ShowActor] = Field(default_factory=list)
    """The assignments of each role"""
    statuses: list[EpisodeStatus] = Field(default_factory=list)
    """The status of each episode"""

    show_id: UUID = Field(default_factory=make_uuid)
    """The ID of this project."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """
    The integrations of this project.
    Can be used to link to other services like Discord, role checking,
    announcement channels, etc.
    """
    created_at: DateTime = Field(default_factory=pendulum_utc)
    """The time this project was created."""
    updated_at: DateTime = Field(default_factory=pendulum_utc)
    """The time this project was last updated."""

    @after_event(*AllEvent)
    def coerce_penulum(self):
        _coerce_to_pendulum(self)

    def _save_state(self):
        _coerce_to_pendulum(self)
        super()._save_state()

    class Settings:
        name = "ShowtimesProjects"
        use_state_management = True


class UserType(str, Enum):
    """
    The user type
    """

    USER = "USER"
    ADMIN = "ADMIN"


class ShowtimesUserDiscord(BaseModel):
    """
    The discord metadata of the user.

    Used for OAuth2.
    """

    id: str
    name: str
    access_token: str
    refresh_token: str
    expires_at: float


class _UserDocType(str, Enum):
    USER = "USER"
    TEMPUSER = "TEMPUSER"
    UNKNOWN = "UNKNOWN"


class ShowtimesUserGroup(Document):
    username: str
    """The username or the name of the user."""
    cls_id: _UserDocType = Field(default=_UserDocType.UNKNOWN)
    """The class ID of the user, used for inheritance."""
    user_id: UUID = Field(default_factory=make_uuid)
    """The ID of the user."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """The integrations of this user."""

    class Settings:
        name = "ShowtimesUsers"
        is_root = True
        use_state_management = True

    def is_temp_user(self) -> bool:
        """
        Check if the user is a temporary user.
        """
        return self.cls_id == _UserDocType.TEMPUSER


class ShowtimesUser(ShowtimesUserGroup):
    """
    The user authentication and more.
    """

    privilege: UserType
    """The privilege of the user."""
    password: Optional[str] = None
    """Hashed password, ARGON2ID"""
    name: Optional[str] = None
    """The full name of the user."""
    discord_meta: Optional[ShowtimesUserDiscord] = None
    """Discord OAuth2 information"""
    avatar: Optional[ImageMetadata] = None
    """Avatar of the user"""
    api_key: Optional[str] = None
    """Authentication API key"""

    @before_event(*AllEvent)
    def make_sure(self):
        self.cls_id = _UserDocType.USER
        if self.password is None and self.discord_meta is None:
            raise ValueError("Password or Discord metadata must be provided.")


class ShowtimesTempUserType(str, Enum):
    """
    The temporary user type
    """

    REGISTER = "REGISTER"
    """New user registration"""
    MIGRATION = "MIGRATION"
    """Old user migration that does not have password or discord_meta"""


class ShowtimesTemporaryUser(ShowtimesUserGroup):
    """
    A temporary model to hold the register information.
    """

    password: str
    """:class:`str`: The password of the user."""
    type: ShowtimesTempUserType
    """:class:`ShowtimesTempUserType`: The type of the temporary user."""

    approval_code: str = Field(default_factory=lambda: generate_custom_code(16, True, True))
    """:class:`str`: The approval code of the user."""

    @before_event(*AllEvent)
    def persist_type(self):
        self.cls_id = _UserDocType.TEMPUSER

    def to_user(self, hashed_password: str | None = None) -> ShowtimesUser:
        """
        Convert the temporary user to a real user.
        """
        return ShowtimesUser(
            username=self.username,
            password=hashed_password or self.password,
            privilege=UserType.USER,
            user_id=self.user_id,
        )


class ShowtimesServer(Document):
    """
    The account that basically the administrator of the projects.
    Is called "server" since it's a carry over from the original
    Discord bot implementations.
    """

    name: str
    """The name of the server."""
    projects: list[Link[ShowProject]] = Field(default_factory=list)
    """The projects of this server."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """The integrations of this server."""
    owners: list[Link[ShowtimesUserGroup]] = Field(default_factory=list)
    """The owners of this server."""
    avatar: Optional[ImageMetadata] = None
    """The avatar link of this server."""

    server_id: UUID = Field(default_factory=make_uuid)

    class Settings:
        name = "ShowtimesServers"
        use_state_management = True


class ShowtimesCollaborationInfo(BaseModel):
    """
    The collaboration info data for the document.
    """

    server: Link[ShowtimesServer]
    project: Optional[Link[ShowProject]] = None


class ShowtimesCollaboration(Document):
    """
    The collaboration document.
    """

    code: str
    """The code of the collaboration."""
    source: ShowtimesCollaborationInfo
    """The source server of the collaboration."""
    target: ShowtimesCollaborationInfo
    """The target server of the collaboration."""

    collab_id: UUID = Field(default_factory=make_uuid)

    @before_event(*AllEvent)
    def verify_source(self):
        if self.source.project is None:
            raise ValueError("Source project must be provided.")

    class Settings:
        name = "ShowtimesCollaborations"
        use_state_management = True


class ShowtimesCollaborationLinkSync(Document):
    """
    The collaboration link document.
    """

    projects: list[UUID] = Field(default_factory=list)
    """The projects of the collaboration, must be the same external ID."""
    servers: list[UUID] = Field(default_factory=list)
    """The servers that joined the collaboration."""
