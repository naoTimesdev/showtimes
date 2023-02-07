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

# Created manually because mypy are unable to auto generate stubs for tantivy.
# It should cover all the usable APIs of tantivy.
# Anything with a leading underscore is not considered as a public API.
# and only used internally by tantivy itself and should not be used by users.
# The private types are mainly used for completion and type checking.

# TODO: Add docstrings for all the classes and methods.

from datetime import datetime
from typing import Any, Generic, Literal, Optional, TypeAlias, TypeVar

# Private types, cannot be imported from tantivy itself.
_DefaultTokenizer: TypeAlias = Literal["default", "raw", "en_stem", "whitespace"]
_IndexOptions: TypeAlias = Literal["position", "basic", "freq"]
_FastOptions: TypeAlias = Literal["single", "multi"]
_ReloadPolicyOptions: TypeAlias = Literal["oncommit", "manual"]
_OpStamp: TypeAlias = int
_SchemaT = TypeVar("_SchemaT", bound=Schema)

class Schema(Generic[_SchemaT]): ...

class SchemaBuilder(Generic[_SchemaT]):
    def __init__(self) -> None: ...
    def add_text_field(
        self, name: str, stored: bool = ..., tokenizer_name: _DefaultTokenizer = ..., index_option: _IndexOptions = ...
    ) -> None: ...
    def add_integer_field(
        self, name: str, stored: bool = ..., indexed: bool = ..., fast: _FastOptions | None = ...
    ) -> None: ...
    def add_unsigned_field(
        self, name: str, stored: bool = ..., indexed: bool = ..., fast: _FastOptions | None = ...
    ): ...
    def add_date_field(self, name: str, stored: bool = ..., indexed: bool = ..., fast: _FastOptions | None = ...): ...
    def add_json_field(
        self, name: str, stored: bool = ..., tokenizer_name: _DefaultTokenizer = ..., index_option: _IndexOptions = ...
    ): ...
    def add_facet_field(self, name: str): ...
    def add_bytes_field(self, name: str): ...
    def build(self) -> Schema[_SchemaT]: ...

class Facet:
    @classmethod
    def root(cls) -> Facet: ...
    @property
    def is_root(self) -> bool: ...
    def is_prefix_of(self, other: Facet) -> bool: ...
    @classmethod
    def from_string(cls, facet_string: str) -> Facet: ...
    def to_path(self) -> list[str]: ...
    def to_path_str(self) -> str: ...

class Document:
    def __init__(self, **kwargs) -> None: ...
    def extend(self, **kwargs) -> None: ...
    @staticmethod
    def from_dict(data: dict[str, Any]) -> Document: ...
    def to_dict(self) -> dict[str, Any]: ...
    def add_text(self, field_name: str, text: str) -> None: ...
    def add_unsigned(self, field_name: str, value: int) -> None: ...
    def add_integer(self, field_name: str, value: int) -> None: ...
    def add_date(self, field_name: str, value: datetime) -> None: ...
    def add_facet(self, field_name: str, value: Facet) -> None: ...
    def add_bytes(self, field_name: str, value: bytes) -> None: ...
    def add_json(self, field_name: str, value: str) -> None: ...
    @property
    def num_fields(self) -> int: ...
    @property
    def is_empty(self) -> bool: ...
    def get_first(self, field_name: str) -> Any: ...
    def get_all(self, field_name: str) -> list[Any]: ...
    def __getitem__(self, field_name: str) -> list[Any]: ...

class _IndexWriter:
    def add_document(self, document: Document) -> _OpStamp: ...
    def add_json(self, json: str) -> _OpStamp: ...
    def commit(self) -> _OpStamp: ...
    def rollback(self) -> _OpStamp: ...
    def delete_documents(self, field_name: str, field_value: Any) -> _OpStamp: ...
    @property
    def commit_opstamp(self) -> _OpStamp: ...

class Query: ...

class DocAddress:
    @property
    def segment_ord(self) -> int: ...
    @property
    def doc(self) -> int: ...

class SearchResult:
    @property
    def hits(self) -> list[tuple[int, DocAddress]]: ...
    @property
    def count(self) -> int: ...

class Searcher:
    def search(
        self, query: Query, limit: int = ..., count: bool = True, order_by_field: Optional[str] = ..., offset: int = ...
    ) -> SearchResult: ...
    @property
    def num_docs(self) -> int: ...
    def doc(self, doc_address: DocAddress) -> Document: ...

class Index:
    def __init__(self, schema: Schema, path: str | None = ..., reuse: bool = ...) -> None: ...
    @staticmethod
    def open(path: str) -> Index: ...
    def writer(self, heap_size: int = ..., num_threads: int = ...) -> _IndexWriter: ...
    def config_reader(self, reload_policy: _ReloadPolicyOptions = ..., num_searchers: int = ...) -> None: ...
    def searcher(self) -> Searcher: ...
    @staticmethod
    def exists(path: str) -> bool: ...
    @property
    def schema(self) -> Schema: ...
    def reload(self) -> None: ...
    def parse_query(self, query: str, default_field_names: list[str] | None) -> Query: ...