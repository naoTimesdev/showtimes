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

from enum import Enum
from typing import Optional
from uuid import UUID

# import strawberry as gql
from beanie import Document, Insert, Link, PydanticObjectId, Replace, SaveChanges, Update, before_event
from pendulum.datetime import DateTime
from pydantic import BaseModel, Field

from ..utils import make_uuid
from ._doc import _coerce_to_pendulum, pendulum_utc


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
    finished: bool = Field(default=False)


class RoleActor(Document):
    """
    The actor model, only exists once per actor.
    """

    name: str
    avatar: str
    integrations: list[IntegrationId] = Field(default_factory=list)
    actor_id: UUID = Field(default_factory=make_uuid)

    class Settings:
        name = "ShowtimesActors"
        use_state_management = True


# Default roles for each show.
DEFAULT_ROLES = [
    RoleStatus(key="TL", name="Translator"),
    RoleStatus(key="TLC", name="Translation Checker"),
    RoleStatus(key="ENC", name="Encoder"),
    RoleStatus(key="ED", name="Editor"),
    RoleStatus(key="TS", name="Typesetter"),
    RoleStatus(key="TM", name="Timer"),
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
    statuses: list[RoleStatus] = Field(default_factory=lambda: DEFAULT_ROLES)
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
    actor: Optional[Link[RoleActor]] = None


class ShowPoster(BaseModel):
    url: str
    """The URL to the poster."""
    color: Optional[int] = None
    """The int color of the poster, representation only."""


class ShowExternalType(str, Enum):
    ANILIST = "ANILIST"
    TMDB = "THEMOVIEDB"

    UNKNOWN = "INVALID_EXTERNAL_TYPE"


class ShowExternalEpisode(BaseModel):
    episode: int
    season: int = Field(default=1)
    title: Optional[str] = None
    airtime: Optional[float] = None


class ShowExternalData(Document):
    episodes: list[ShowExternalEpisode] = Field(default_factory=list)
    type: ShowExternalType = ShowExternalType.UNKNOWN

    class Settings:
        name = "ShowtimesExternals"
        is_root = True
        use_state_management = True


class ShowExternalAnilist(ShowExternalData):
    ani_id: str
    mal_id: Optional[str] = None  # for other integration
    start_time: Optional[float] = None

    @before_event(Insert, Replace, Update, SaveChanges)
    def force_type(self):
        # DO NOT ALLOW THIS TO BE CHANGED.
        self.type = ShowExternalType.ANILIST


class ShowExternalTMDB(ShowExternalData):
    tmdb_id: str
    start_time: Optional[float] = None

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

    assignments: list[ShowActor] = Field(default_factory=list)
    """The assignments of each role"""
    episodes: list[EpisodeStatus] = Field(default_factory=list)
    """The status of each episode"""
    airtime: Optional[float] = None
    """The unix timestamp of the airing time, if any."""
    collaboration: list[PydanticObjectId] = Field(default_factory=list)
    """The list of collaborators, can be used to link to other projects."""

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _coerce_to_pendulum(self)

    class Settings:
        name = "ShowtimesProjects"
        use_state_management = True


class CollaborationLinkStatus(int, Enum):
    """
    The collaboration link status.
    """

    PENDING = 0
    """The status of the link is pending."""
    ACCEPTED = 1
    """The status of the link is accepted."""
    REJECTED = -1
    """The status of the link is rejected."""
    CANCELLED = -10
    """The status of the link are pending, then cancelled by the source."""
    DROPPED = -99
    """The status of the link are accepted, then dropped after it."""


class ShowCollaborationLink(BaseModel):
    source: Link["ShowtimesServer"]
    project: Link[ShowProject]
    status: CollaborationLinkStatus


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


class ShowtimesUser(Document):
    """
    The user authentication and more.
    """

    username: str
    """The username or the name of the user."""
    password: str
    """Hashed password, ARGON2ID"""
    privilege: UserType
    """The privilege of the user."""
    discord_meta: Optional[ShowtimesUserDiscord] = None

    user_id: UUID = Field(default_factory=make_uuid)

    class Settings:
        name = "ShowtimesUsers"
        use_state_management = True


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
    collaborations: list[ShowCollaborationLink] = Field(default_factory=list)
    """The collaborations of this server."""
    integrations: list[IntegrationId] = Field(default_factory=list)
    """The integrations of this server."""
    owners: list[Link[ShowtimesUser]] = Field(default_factory=list)
    """The owners of this server."""

    server_id: UUID = Field(default_factory=make_uuid)

    class Settings:
        name = "ShowtimesServers"
        use_state_management = True
