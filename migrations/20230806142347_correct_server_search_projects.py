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

from pathlib import Path

from beanie import free_fall_migration

from showtimes.controllers.searcher import get_searcher, init_searcher
from showtimes.graphql.mutations.common import query_aggregate_project_ids
from showtimes.models.database import ShowProject, ShowtimesServer
from showtimes.models.searchdb import ServerSearch
from showtimes.tooling import get_env_config, setup_logger

CURRENT_DIR = Path(__file__).absolute().parent
ROOT_DIR = CURRENT_DIR.parent
logger = setup_logger(ROOT_DIR / "logs" / "migrations.log")


class Forward:
    @free_fall_migration(document_models=[ShowtimesServer, ShowProject])
    async def correct_server_search_projects(self, session):
        env_config = get_env_config(include_environ=True)

        logger.info("Creating Meilisearch client instances...")
        MEILI_URL = env_config.get("MEILI_URL")
        MEILI_API_KEY = env_config.get("MEILI_API_KEY")
        if MEILI_URL is None or MEILI_API_KEY is None:
            raise RuntimeError("No Meilisearch URL or API key specified")

        await init_searcher(MEILI_URL, MEILI_API_KEY)
        logger.info("Meilisearch client instances created!")
        meili_client = get_searcher()

        search_proj_docs: list[ServerSearch] = []
        logger.info("Querying all Showtimes servers...")
        async for server in ShowtimesServer.find(session=session):
            project_ids = [project.ref.id for project in server.projects]
            logger.info(f"  Querying projects for server {server.server_id}...")
            projects = await query_aggregate_project_ids(project_ids)
            server_search = ServerSearch.from_db(server)
            server_search.projects = [str(proj.show_id) for proj in projects]
            search_proj_docs.append(server_search)

        logger.info("Updating Meilisearch documents...")
        await meili_client.update_documents(search_proj_docs)  # type: ignore

        logger.info("Closing Meilisearch client instances...")
        await meili_client.close()
        logger.info("Closed Meilisearch client instances!")


class Backward:
    ...
