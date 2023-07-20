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

import functools
import os
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request, WebSocket
from fastapi.datastructures import Default

from showtimes.controllers.claim import get_claim_status
from showtimes.controllers.database import ShowtimesDatabase
from showtimes.controllers.searcher import get_searcher, init_searcher
from showtimes.controllers.sessions.errors import SessionError
from showtimes.controllers.sessions.handler import check_session, create_session_handler, get_session_handler
from showtimes.controllers.storages import S3Storage, get_s3_storage, init_s3_storage
from showtimes.extensions.fastapi.discovery import discover_routes
from showtimes.extensions.fastapi.responses import ORJSONXResponse, ResponseType
from showtimes.extensions.graphql.context import SessionQLContext
from showtimes.extensions.graphql.router import SessionGraphQLRouter
from showtimes.graphql.schema import make_schema
from showtimes.utils import to_boolean, try_int

from ._metadata import __description__ as app_description
from ._metadata import __license__ as app_license
from ._metadata import __version__ as app_version
from .tooling import get_env_config, setup_logger

__all__ = (
    "create_app",
    "get_root_logger",
)
CURRENT_DIR = Path(__file__).absolute().parent
ROOT_DIR = CURRENT_DIR.parent
_GlobalLogger = setup_logger(ROOT_DIR / "logs" / "server.log")


def get_root_logger():
    return _GlobalLogger


async def app_on_startup(run_production: bool = True):
    logger = get_root_logger()
    env_config = get_env_config(run_production)
    logger.info("Environment configuration loaded: %s", env_config)
    logger.info("Starting server...")
    logger.info("Connecting to Showtimes database...")

    DB_URL = env_config.get("MONGODB_URL")
    DB_HOST = env_config.get("MONGODB_HOST")
    DB_PORT = env_config.get("MONGODB_PORT")
    DB_NAME = env_config.get("MONGODB_DBNAME")
    DB_AUTH_STRING = env_config.get("MONGODB_AUTH_STRING")
    DB_AUTH_SOURCE = env_config.get("MONGODB_AUTH_SOURCE")
    DB_AUTH_TLS = to_boolean(env_config.get("MONGODB_TLS"))
    dbname_fb = "naotimesdb"
    if not run_production:
        dbname_fb += "_dev"
    if DB_URL is not None:
        shdb = ShowtimesDatabase(DB_URL, dbname=DB_NAME or dbname_fb)
    elif DB_HOST is not None:
        shdb = ShowtimesDatabase(
            DB_HOST,
            try_int(DB_PORT) or 27017,
            DB_NAME or "showtimesdb",
            DB_AUTH_STRING,
            DB_AUTH_SOURCE or "admin",
            DB_AUTH_TLS,
        )
    else:
        raise RuntimeError("No database URL or host specified")

    await shdb.connect()
    logger.info("Connected to Showtimes database")

    logger.info("Checking claim status from DB...")
    claim_latch = get_claim_status()
    await claim_latch.set_from_db()
    logger.info(f"Server claim status: {claim_latch.claimed}")

    S3_HOST = env_config.get("S3_HOST")
    S3_KEY = env_config.get("S3_ACCESS_KEY")
    S3_SECRET = env_config.get("S3_SECRET_KEY")
    S3_REGION = env_config.get("S3_REGION")
    S3_BUCKET = env_config.get("S3_BUCKET")

    if S3_SECRET is not None and S3_KEY is not None and S3_BUCKET is not None:
        logger.info("Initializing S3 storage...")
        await init_s3_storage(S3_BUCKET, S3_KEY, S3_SECRET, S3_REGION, host=S3_HOST)
        logger.info("S3 storage initialized!")

    logger.info("Creating session...")
    DEFAULT_KEY = "SHOWTIMES_BACKEND_SECRET"
    SECRET_KEY = env_config.get("SECRET_KEY") or DEFAULT_KEY
    REDIS_HOST = env_config.get("REDIS_HOST")
    REDIS_PORT = env_config.get("REDIS_PORT")
    REDIS_PASS = env_config.get("REDIS_PASS")
    if SECRET_KEY == DEFAULT_KEY:
        logger.warning("Using default secret key, please change it later since it's not secure!")
    SESSION_MAX_AGE = int(env_config.get("SESSION_MAX_AGE") or 7 * 24 * 60 * 60)
    logger.info(f"Creating session handler with max age of {SESSION_MAX_AGE} seconds...")
    await create_session_handler(SECRET_KEY, REDIS_HOST, try_int(REDIS_PORT) or 6379, REDIS_PASS, SESSION_MAX_AGE)
    logger.info("Session created!")

    logger.info("Creating Meilisearch client instances...")
    MEILI_URL = env_config.get("MEILI_URL")
    MEILI_API_KEY = env_config.get("MEILI_API_KEY")
    if MEILI_URL is None or MEILI_API_KEY is None:
        raise RuntimeError("No Meilisearch URL or API key specified")

    await init_searcher(MEILI_URL, MEILI_API_KEY)
    logger.info("Meilisearch client instances created!")


async def app_on_shutdown():
    logger = get_root_logger()
    logger.info("Shutting down backend...")
    # logger.info("Closed storage connection!")
    # pubsub = get_pubsub()
    # logger.info("Closing pubsub connection...")
    # await pubsub.close()
    # logger.info("Closed pubsub connection!")

    try:
        logger.info("Closing redis session backend...")
        session_handler = get_session_handler()
        await session_handler.backend.shutdown()
        logger.info("Closed redis session backend!")
    except Exception as exc:
        logger.error("Failed to close redis session backend: %s", exc, exc_info=exc)

    stor_s3: S3Storage | None = None
    try:
        stor_s3 = get_s3_storage()
    except RuntimeError:
        pass

    if stor_s3 is not None:
        logger.info("Closing S3 storage...")
        await stor_s3.close()
        logger.info("Closed S3 storage!")

    try:
        meili_search = get_searcher()
        logger.info("Closing Meilisearch client instances...")
        await meili_search.close()
        logger.info("Closed Meilisearch client instances!")
    except RuntimeError:
        pass


async def exceptions_handler_session_error(_: Request, exc: SessionError):
    status_code = exc.status_code
    if status_code < 400:
        status_code = 403
    return ResponseType(error=exc.detail, code=status_code).to_orjson(status_code)


async def context_handler_gql_session(request: Request, websocket: WebSocket):
    if request is None and websocket is None:
        raise ValueError("Either request or websocket must be provided")
    session = get_session_handler()
    try:
        user = await check_session(request or websocket)  # type: ignore
        return SessionQLContext(session=session, user=user)
    except Exception:
        return SessionQLContext(session=session)


async def context_gql_handler(
    custom_context=Depends(context_handler_gql_session),
):
    claim_stat = get_claim_status()
    if not claim_stat.claimed:
        raise RuntimeError("Server is not claimed")
    return custom_context


def create_app():
    logger = get_root_logger()
    logger.info("Creating backend app...")
    app = FastAPI(
        title="Showtimes API",
        description=app_description,
        version=app_version,
        license_info={
            "name": app_license,
            "url": "https://github.com/naoTimesdev/showtimes/blob/master/LICENSE",
        },
        contact={"url": "https://github.com/naoTimesdev/showtimes/"},
    )

    run_dev = to_boolean(os.environ.get("DEVELOPMENT", "0"))
    logger.info(f"Running in {'development' if run_dev else 'production'} mode")
    app.router.add_event_handler("startup", functools.partial(app_on_startup, run_production=not run_dev))
    app.router.add_event_handler("shutdown", app_on_shutdown)
    app.add_exception_handler(SessionError, exceptions_handler_session_error)

    # --> Router API
    logger.info("Discovering routes...")
    api_router = APIRouter(prefix="/api")

    ORJSONXDefault = Default(ORJSONXResponse)
    routes_folder = CURRENT_DIR / "routes"
    loaded_routes = discover_routes(
        app_or_router=api_router, route_path=routes_folder, recursive=True, default_response_class=ORJSONXDefault
    )
    logger.info(f"Loaded {len(loaded_routes)} routes!")
    # <--

    # --> GraphQL Router
    logger.info("Preparing GraphQL router...")
    graphql_router = SessionGraphQLRouter(
        path="/graphql",
        schema=make_schema(),
        context_getter=context_gql_handler,
    )
    # <--

    # --> Include Router
    logger.info("Binding routes...")
    app.include_router(api_router)
    app.include_router(graphql_router)
    # <--

    @app.get("/", include_in_schema=False)
    async def _root_api_redirect():
        return ORJSONXResponse(content={"status": "ok"})

    logger.info("Backend app created!")
    return app
