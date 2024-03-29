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

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, WebSocket
from fastapi.datastructures import Default
from fastapi.middleware import Middleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from strawberry.exceptions import StrawberryGraphQLError

from showtimes.controllers.anilist import get_anilist_client, init_anilist_client
from showtimes.controllers.claim import get_claim_status
from showtimes.controllers.database import ShowtimesDatabase
from showtimes.controllers.prediction import load_prediction_models
from showtimes.controllers.pubsub import get_pubsub
from showtimes.controllers.redisdb import get_redis, init_redis_client
from showtimes.controllers.searcher import get_searcher, init_searcher
from showtimes.controllers.sessions.errors import SessionError
from showtimes.controllers.sessions.handler import check_session, create_session_handler, get_session_handler
from showtimes.controllers.showrss import get_showrss, initialize_showrss
from showtimes.controllers.storages import S3Storage, get_s3_storage, init_s3_storage
from showtimes.controllers.tmdb import get_tmdb_client, init_tmdb_client
from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.extensions.fastapi.discovery import discover_routes
from showtimes.extensions.fastapi.errors import ShowtimesException
from showtimes.extensions.fastapi.lock import get_ready_status
from showtimes.extensions.fastapi.responses import ORJSONXResponse, ResponseType
from showtimes.extensions.graphql.context import SessionQLContext
from showtimes.extensions.graphql.router import SessionGraphQLRouter
from showtimes.graphql.schema import make_schema
from showtimes.models.searchdb import ProjectSearch, ServerSearch, UserSearch
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
TEMPLATE_DIR = CURRENT_DIR / "templates"
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

    S3_ENDPOINT = env_config.get("S3_ENDPOINT")
    S3_KEY = env_config.get("S3_ACCESS_KEY")
    S3_SECRET = env_config.get("S3_SECRET_KEY")
    S3_REGION = env_config.get("S3_REGION")
    S3_BUCKET = env_config.get("S3_BUCKET")

    if S3_SECRET is not None and S3_KEY is not None and S3_BUCKET is not None:
        logger.info("Initializing S3 storage...")
        await init_s3_storage(S3_BUCKET, S3_KEY, S3_SECRET, S3_REGION, endpoint=S3_ENDPOINT)
        logger.info("S3 storage initialized!")

    logger.info("Creating session...")
    DEFAULT_KEY = "SHOWTIMES_BACKEND_SECRET"
    SECRET_KEY = env_config.get("SECRET_KEY") or DEFAULT_KEY
    REDIS_HOST = env_config.get("REDIS_HOST")
    REDIS_PORT = env_config.get("REDIS_PORT")
    REDIS_PASS = env_config.get("REDIS_PASS")
    if SECRET_KEY == DEFAULT_KEY:
        logger.warning("Using default SECRET_KEY, please change it later since it's not secure!")
    logger.info("Connecting to redis session backend...")
    await init_redis_client(REDIS_HOST or "localhost", try_int(REDIS_PORT) or 6379, REDIS_PASS)
    logger.info("Connected to redis session backend!")
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
    logger.info("Meilisearch client instances created! Setting up index configuration...")

    searcher = get_searcher()
    await searcher.update_schema_settings(ProjectSearch)
    await searcher.update_schema_settings(ServerSearch)
    await searcher.update_schema_settings(UserSearch)

    # Initialize other stuff here
    logger.info("Creating Anilist client instances...")
    await init_anilist_client()
    TMDB_API_KEY = env_config.get("TMDB_API_KEY")
    if TMDB_API_KEY is not None:
        logger.info("Creating TMDb client instances...")
        await init_tmdb_client(TMDB_API_KEY)

    logger.info("Loading prediction model...")
    await load_prediction_models()

    logger.info("Loading ShowRSS feeds...")
    SHOWRSS_INTERVAL = try_int(env_config.get("SHOWRSS_INTERVAL"), 300)
    SHOWRSS_INTEVAL_PREMIUM = try_int(env_config.get("SHOWRSS_INTERVAL_PREMIUM"), 180)
    SHOWRSS_LIMIT = try_int(env_config.get("SHOWRSS_LIMIT"), 3)
    SHOWRSS_LIMIT_PREMIUM = try_int(env_config.get("SHOWRSS_LIMIT_PREMIUM"), 5)

    if SHOWRSS_INTERVAL < 60:
        raise RuntimeError("SHOWRSS_INTERVAL must be at least 60 seconds")
    if SHOWRSS_INTEVAL_PREMIUM < 60:
        raise RuntimeError("SHOWRSS_INTERVAL_PREMIUM must be at least 60 seconds")
    if SHOWRSS_LIMIT < 1:
        raise RuntimeError("SHOWRSS_LIMIT must be at least 1")
    if SHOWRSS_LIMIT_PREMIUM < 1:
        raise RuntimeError("SHOWRSS_LIMIT_PREMIUM must be at least 1")

    await initialize_showrss(
        SHOWRSS_INTERVAL,
        SHOWRSS_INTEVAL_PREMIUM,
        SHOWRSS_LIMIT,
        SHOWRSS_LIMIT_PREMIUM,
    )

    # Ready latch
    logger.info("Server is ready!")
    get_ready_status().ready()


async def app_on_shutdown():
    logger = get_root_logger()
    logger.info("Shutting down backend...")

    try:
        showrss = get_showrss()
        logger.info("Closing ShowRSS instances...")
        await showrss.close()
        logger.info("Closed ShowRSS instances!")
    except ShowtimesControllerUninitializedError:
        pass

    pubsub = get_pubsub()
    logger.info("Closing PubSub instances...")
    await pubsub.close()
    logger.info("Closed PubSub instances!")

    try:
        redis_client = get_redis()
        logger.info("Closing Redis client instances...")
        await redis_client.close()
        logger.info("Closed Redis client instances!")
    except ShowtimesControllerUninitializedError:
        pass

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
    except ShowtimesControllerUninitializedError:
        pass

    if stor_s3 is not None:
        logger.info("Closing S3 storage...")
        await stor_s3.close()
        logger.info("Closed S3 storage!")

    try:
        meili_client = get_searcher()
        logger.info("Closing Meilisearch client instances...")
        await meili_client.close()
        logger.info("Closed Meilisearch client instances!")
    except ShowtimesControllerUninitializedError:
        pass

    try:
        anilist_client = get_anilist_client()
        logger.info("Closing Anilist client instances...")
        await anilist_client.close()
        logger.info("Closed Anilist client instances!")
    except ShowtimesControllerUninitializedError:
        pass

    try:
        tmdb_client = get_tmdb_client()
        logger.info("Closing TMDb client instances...")
        await tmdb_client.close()
        logger.info("Closed TMDb client instances!")
    except ShowtimesControllerUninitializedError:
        pass


def make_graphql_error_response(exc: HTTPException, error_message: str, error_type: str):
    status_code = exc.status_code
    if status_code < 400:
        status_code = 403
    fmt_error = StrawberryGraphQLError(
        error_message,
        extensions={"type": error_type, "code": status_code, "detail": exc.detail},
    ).formatted

    return ORJSONXResponse(content={"errors": [fmt_error], "data": None}, status_code=status_code)


async def exceptions_handler_session_error(req: Request, exc: SessionError):
    if "graphql" in req.url.path:
        return make_graphql_error_response(
            exc, "Unable to authorize session, see extensions for more info", "SESSION_ERROR"
        )
    status_code = exc.status_code
    if status_code < 400:
        status_code = 403
    return ResponseType(error=exc.detail, code=status_code).to_orjson(status_code)


async def exceptions_handler_showtimes_error(req: Request, exc: ShowtimesException):
    if "graphql" in req.url.path:
        return make_graphql_error_response(exc, "Unable to process request", "SHOWTIMES_EXCEPTION")
    status_code = exc.status_code
    if status_code < 400:
        status_code = 403
    return ResponseType(error=exc.detail, code=status_code).to_orjson(status_code)


async def context_handler_gql_session(
    background_tasks: BackgroundTasks,
    request: Request = None,  # type: ignore
    websocket: WebSocket = None,  # type: ignore
):
    if request is None and websocket is None:
        raise ShowtimesException(500, "Unable to get request/websocket context")
    session = get_session_handler()
    context = SessionQLContext(session=session)
    context.request = request or websocket
    context.background_tasks = background_tasks

    try:
        user = await check_session(request or websocket)  # type: ignore
        context.user = user
    except Exception:  # noqa: S110
        pass
    return context


def verify_server_ready():
    ready_latch = get_ready_status()
    if not ready_latch.is_ready():
        raise ShowtimesException(503, "Server is not ready yet")


async def context_gql_handler(
    request_context=Depends(context_handler_gql_session),
):
    verify_server_ready()

    claim_stat = get_claim_status()
    if not claim_stat.claimed:
        raise ShowtimesException(503, "Server is not claimed yet")
    return request_context


def create_app():
    logger = get_root_logger()
    # Initialize latch
    get_ready_status().unready()
    logger.info(f"Initializing Showtimes v{app_version}...")
    app = FastAPI(
        title="Showtimes API",
        description=app_description,
        version=app_version,
        license_info={
            "name": app_license,
            "url": "https://github.com/naoTimesdev/showtimes/blob/master/LICENSE",
        },
        contact={"url": "https://github.com/naoTimesdev/showtimes/"},
        terms_of_service="https://naoti.me/terms",
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["Authorization", "Cookie"],
            ),
        ],
    )
    ASSETS_FOLDER = CURRENT_DIR / "assets"
    app.mount("/assets", StaticFiles(directory=ASSETS_FOLDER), name="assets")

    run_dev = to_boolean(os.environ.get("DEVELOPMENT", "0"))
    env_conf = get_env_config(not run_dev)
    if not env_conf.get("MASTER_KEY"):
        raise RuntimeError("No MASTER_KEY specified")
    logger.info(f"Running in {'development' if run_dev else 'production'} mode")
    app.router.add_event_handler("startup", functools.partial(app_on_startup, run_production=not run_dev))
    app.router.add_event_handler("shutdown", app_on_shutdown)
    app.add_exception_handler(SessionError, exceptions_handler_session_error)
    app.add_exception_handler(ShowtimesException, exceptions_handler_showtimes_error)

    # --> Router API
    logger.info("Discovering routes...")
    api_router = APIRouter(dependencies=[Depends(verify_server_ready)])

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
    app.include_router(graphql_router, tags=["GraphQL"])
    # <--

    @app.get("/", include_in_schema=False)
    async def _root_api_welcome():
        ready = get_ready_status().is_ready()
        return ORJSONXResponse(content={"status": "ok" if ready else "waiting"}, status_code=200 if ready else 503)

    @app.get("/claim", include_in_schema=False, response_class=HTMLResponse)
    async def _root_claim_webpage():
        claim_stat = get_claim_status()
        if claim_stat.claimed:
            return RedirectResponse("/graphql")

        ClaimWebpage = HTMLResponse((TEMPLATE_DIR / "claim.html").read_text())
        return ClaimWebpage

    @app.get("/favicon.ico", include_in_schema=False)
    def _root_favicon():
        return FileResponse(ASSETS_FOLDER / "favicon.ico")

    # Disable robots
    @app.get("/robots.txt", include_in_schema=False)
    def _root_robots_txt():
        DISALLOWED = ["*", "AdsBot-Google"]
        ALLOWED = []
        robots_txt = []
        if DISALLOWED:
            for disallow in DISALLOWED:
                robots_txt.append(f"User-agent: {disallow}")
            robots_txt.append("Disallow: /\n")
        if ALLOWED:
            for allow in ALLOWED:
                robots_txt.append(f"User-agent: {allow}")
            robots_txt.append("Disallow: /")
        return PlainTextResponse("\n".join(robots_txt))

    logger.info(f"Showtimes v{app_version} is ready, now accepting requests via Starlette!")
    return app
