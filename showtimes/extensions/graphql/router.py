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
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
from starlette import status
from strawberry.exceptions import MissingQueryError
from strawberry.fastapi import GraphQLRouter
from strawberry.http import parse_request_data
from strawberry.schema.exceptions import InvalidOperationTypeError
from strawberry.types.graphql import OperationType

from showtimes.controllers.sessions import SessionError
from showtimes.extensions.fastapi import ORJSONXResponse
from showtimes.models.session import UserSession

from .context import SessionQLContext

__all__ = ("SessionGraphQLRouter",)

logger = logging.getLogger("GraphQL.Router")


class SessionGraphQLRouter(GraphQLRouter):
    async def execute_request(
        self, request: Request, response: Response, data: dict, context: SessionQLContext, root_value
    ) -> Response:
        try:
            request_data = parse_request_data(data)
        except MissingQueryError:
            missing_query_response = PlainTextResponse(
                "No GraphQL query found in the request",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
            return self._merge_responses(response, missing_query_response)

        method = request.method
        allowed_operation_types = OperationType.from_http(method)

        if not self.allow_queries_via_get and method == "GET":
            allowed_operation_types = allowed_operation_types - {OperationType.QUERY}

        try:
            result = await self.execute(
                request_data.query,
                variables=request_data.variables,
                context=context,
                operation_name=request_data.operation_name,
                root_value=root_value,
                allowed_operation_types=allowed_operation_types,
            )
        except InvalidOperationTypeError as e:
            return PlainTextResponse(
                e.as_http_error_reason(method),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        response_data = await self.process_result(request, result)

        # <-- Extension: Change response to ORJSONXResponse
        actual_response: ORJSONXResponse = ORJSONXResponse(
            response_data,
            status_code=status.HTTP_200_OK,
        )
        # -->
        # <-- Extension: Add session updater using latch
        if context.session_latch:
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
                    await context.session.remove_session(cr_user.session_id, actual_response)
            else:
                await context.session.set_session(context.user, actual_response)
        # -->

        return self._merge_responses(response, actual_response)
