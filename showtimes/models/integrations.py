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

from functools import cached_property

from beanie import Insert, Replace, SaveChanges, Update, before_event
from pydantic import BaseModel

__all__ = (
    "IntegrationId",
    "DefaultIntegrationType",
)


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

    @cached_property
    def all(self) -> dict[str, str]:
        """:class:`dict[str, str]`: All the default type mappings."""
        invalid_dir = ["all", "verify"]
        return {k: getattr(self, k) for k in dir(self) if not k.startswith("__") and k not in invalid_dir}

    @classmethod
    def verify(cls: type[DefaultIntegrationType], input_type: str) -> bool:
        """Verify if the input type is valid.

        Parameters
        ----------
        input_type: :class:`str`
            The input type to verify.

        Returns
        -------
        :class:`bool`
            Whether the input type is valid or not.
        """
        all_inputs = cls().all
        if input_type.startswith(cls.PrefixAnnounce):
            input_type = input_type.replace(cls.PrefixAnnounce, "", 1)
        return input_type in all_inputs.values()
