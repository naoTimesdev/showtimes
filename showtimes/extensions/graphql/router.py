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

import logging
from typing import Any, Optional

import orjson
from fastapi import Request, Response
from strawberry import UNSET
from strawberry.fastapi import GraphQLRouter
from strawberry.http import GraphQLHTTPResponse

from showtimes.controllers.sessions import SessionError
from showtimes.extensions.fastapi.responses import ORJsonEncoder
from showtimes.models.session import UserSession

from .context import SessionQLContext

__all__ = ("SessionGraphQLRouter",)

logger = logging.getLogger("GraphQL.Router")


class SessionGraphQLRouter(GraphQLRouter):
    def encode_json(self, response_data: GraphQLHTTPResponse) -> str:
        # <-- Extension: Change response to ORJSONXResponse
        return orjson.dumps(
            response_data,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY,
            default=ORJsonEncoder,
        ).decode("utf-8")
        # -->

    async def run(
        self, request: Request, context: SessionQLContext | None = UNSET, root_value: Any | None = UNSET
    ) -> Response:
        response = await super().run(request, context, root_value)

        # <-- Extension: Add session updater using latch
        if isinstance(context, SessionQLContext) and context.session_latch:
            logger.info("Updating session because of latch is True")
            if context.user is None:
                cr_user: Optional[UserSession] = None
                try:
                    cr_user = await context.session(request)
                except SessionError:
                    # Ignore
                    pass
                    # Delete user session
                if cr_user is not None:
                    await context.session.remove_session(cr_user.session_id, response)
            else:
                await context.session.set_or_update_session(context.user, response)
        # -->

        return response
