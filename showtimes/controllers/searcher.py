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

from typing import Any, Generic, Type, TypeVar, overload

import msgspec
from meilisearch_python_async import Client
from meilisearch_python_async.errors import MeilisearchApiError, MeilisearchCommunicationError
from meilisearch_python_async.models.search import SearchResults
from msgspec import Struct

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.models.searchdb import SchemaAble
from showtimes.tooling import get_logger

__all__ = (
    "ShowtimesSearcher",
    "TypedSearchResults",
    "get_searcher",
    "init_searcher",
)
StructT = TypeVar("StructT", bound=Struct)
SchemaT = TypeVar("SchemaT", bound=SchemaAble)


class TypedSearchResults(Struct, Generic[StructT]):
    hits: list[StructT]
    offset: int | None
    limit: int | None
    estimated_total_hits: int | None
    processing_time_ms: int
    query: str
    facet_distribution: dict[str, Any] | None
    total_pages: int | None
    total_hits: int | None
    page: int | None
    hits_per_page: int | None

    @classmethod
    def from_search_results(
        cls: Type["TypedSearchResults"], results: SearchResults, *, type: StructT
    ) -> "TypedSearchResults[StructT]":
        hits_transform: list[StructT] = []
        for result in results.hits:
            decode = msgspec.json.decode(msgspec.json.encode(result), type=type)
            hits_transform.append(decode)

        return cls(
            hits=hits_transform,
            offset=results.offset,
            limit=results.limit,
            estimated_total_hits=results.estimated_total_hits,
            processing_time_ms=results.processing_time_ms,
            query=results.query,
            facet_distribution=results.facet_distribution,
            total_pages=results.total_pages,
            total_hits=results.total_hits,
            page=results.page,
            hits_per_page=results.hits_per_page,
        )


class ShowtimesSearcher(Generic[SchemaT]):
    def __init__(self, meili_url: str, api_key: str) -> None:
        self._client = Client(meili_url, api_key)
        self._logger = get_logger("Showtimes.Controller.Searcher")

    async def test(self) -> bool:
        try:
            await self._client.get_indexes()
            return True
        except (MeilisearchApiError, MeilisearchCommunicationError) as exc:
            self._logger.error("Failed to connect to MeiliSearch: %s", exc, exc_info=exc)
            return False

    async def close(self):
        await self._client.aclose()

    async def add_document(self, document: SchemaT):
        if not issubclass(type(document), SchemaAble):
            raise TypeError("document must be a SchemaAble object.")
        if not hasattr(document, "id"):
            raise TypeError("document must have an id attribute.")

        index = self._client.index(document.Config.index)
        await index.add_documents([document.to_dict()], primary_key="id")

    async def add_documents(self, documents: list[SchemaT]):
        if not all(issubclass(type(document), SchemaAble) for document in documents):
            raise TypeError("all documents must be a SchemaAble object.")
        if not all(hasattr(document, "id") for document in documents):
            raise TypeError("all documents must have an id attribute.")

        group_by_index: dict[str, list[SchemaT]] = {}
        for document in documents:
            group_by_index.setdefault(document.Config.index, []).append(document)
        for index_name, documents in group_by_index.items():
            index = self._client.index(index_name)
            await index.add_documents([document.to_dict() for document in documents], primary_key="id")

    @overload
    async def search(self, index_name: str, query: str, **kwargs) -> SearchResults:
        ...

    @overload
    async def search(self, index_name: str, query: str, *, type: StructT, **kwargs) -> TypedSearchResults[StructT]:
        ...

    @overload
    async def search(self, index_name: str, query: str, *, type: None = ..., **kwargs) -> SearchResults:
        ...

    async def search(
        self, index_name: str, query: str, *, type: StructT | None = None, **kwargs
    ) -> TypedSearchResults[StructT] | SearchResults:
        kwargs.pop("query", None)
        index = self._client.index(index_name)
        reuslts = await index.search(query, **kwargs)
        if type is not None:
            return TypedSearchResults.from_search_results(reuslts, type=type)
        return reuslts

    async def delete_document(self, index_name: str, document_id: str):
        index = self._client.index(index_name)
        await index.delete_document(document_id)

    async def update_document(self, document: SchemaAble):
        if not issubclass(type(document), SchemaAble):
            raise TypeError("document must be a SchemaAble object.")
        if not hasattr(document, "id"):
            raise TypeError("document must have an id attribute.")

        index = self._client.index(document.Config.index)
        await index.update_documents([document.to_dict()], primary_key="id")

    async def update_documents(self, documents: list[SchemaT]):
        if not all(issubclass(type(document), SchemaAble) for document in documents):
            raise TypeError("all documents must be a SchemaAble object.")
        if not all(hasattr(document, "id") for document in documents):
            raise TypeError("all documents must have an id attribute.")

        group_by_index: dict[str, list[SchemaT]] = {}
        for document in documents:
            group_by_index.setdefault(document.Config.index, []).append(document)
        for index_name, documents in group_by_index.items():
            index = self._client.index(index_name)
            await index.update_documents([document.to_dict() for document in documents], primary_key="id")

    async def delete_index(self, index_name: str):
        await self._client.delete_index_if_exists(index_name)

    async def update_facet(self, index_name: str, facet: list[str]):
        index = self._client.index(index_name)
        await index.update_filterable_attributes(facet)

    async def update_schema_settings(self, schema: type[SchemaT]):
        if not hasattr(schema, "Config"):
            raise TypeError("schema must have a Config inner class.")
        index = self._client.index(schema.Config.index)
        try:
            await index.get_settings()
        except MeilisearchApiError as exc:
            if exc.status_code != 404:
                raise
            self._logger.warning("Missing index, creating %s", schema.Config.index)
            index = await self._client.create_index(schema.Config.index, primary_key="id")

        if hasattr(schema.Config, "searchable_fields"):
            self._logger.info("Updating searchable attributes for %s", schema.Config.index)
            await index.update_searchable_attributes(schema.Config.searchable_fields)
        if hasattr(schema.Config, "filterable_fields"):
            self._logger.info("Updating filterable attributes for %s", schema.Config.index)
            await index.update_filterable_attributes(schema.Config.filterable_fields)


_SHOWTIMES_SEARCHER: ShowtimesSearcher | None = None


def get_searcher() -> ShowtimesSearcher:
    global _SHOWTIMES_SEARCHER

    if _SHOWTIMES_SEARCHER is None:
        raise ShowtimesControllerUninitializedError("Showtimes Searcher")

    return _SHOWTIMES_SEARCHER


async def init_searcher(meili_url: str, api_key: str):
    global _SHOWTIMES_SEARCHER

    _SHOWTIMES_SEARCHER = ShowtimesSearcher(meili_url, api_key)
    if not await _SHOWTIMES_SEARCHER.test():
        raise RuntimeError("Failed to connect to MeiliSearch.")
