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

# TODO: Add S3 support

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path
from typing import Any, Coroutine, Optional, Protocol, Union

import pendulum
from aiopath import AsyncPath
from pendulum.datetime import DateTime

__all__ = (
    "FileObject",
    "LocalStorage",
    "get_local_storage",
)


@dataclass
class FileObject:
    filename: str
    content_type: str
    size: int
    last_modified: Optional[DateTime] = None


class StreamableData(Protocol):
    """
    A simple protocol typing for readable data.

    Mainly contains:
    - `.read()` method
    - `.seek()` method

    Both can be async or not.
    """

    def read(self, size: int = -1) -> Union[bytes, Coroutine[Any, Any, bytes]]:
        ...

    def seek(self, offset: int) -> Union[None, Coroutine[Any, Any, None]]:
        ...


async def _run_in_executor(func, *args, **kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    kwargs_args = [val for val in kwargs.values()]
    return await asyncio.get_event_loop().run_in_executor(None, func, *args, *kwargs_args)


class LocalStorage:
    def __init__(self, root_path: Union[Path, AsyncPath]):
        self.__base: AsyncPath = root_path if isinstance(root_path, AsyncPath) else AsyncPath(root_path)
        self._root: AsyncPath = self.__base / "storages"
        self._started = False

    async def start(self):
        if not self._started:
            await self._root.mkdir(exist_ok=True)
            self._started = True

    def close(self):
        pass

    async def stream_upload(self, key: str, key_id: str, filename: str, data: StreamableData, type: str = "images"):
        await self.start()
        path = self._root / type / key / key_id.replace("-", "") / filename
        await path.parent.mkdir(parents=True, exist_ok=True)
        await _run_in_executor(data.seek, 0)
        async with path.open("wb") as f:
            read = await _run_in_executor(data.read, 1024)
            if not read:
                return
            await f.write(read)
        return await self.stat_file(key, key_id, filename, type)

    async def stat_file(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        purepath = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        path = self._root / type / key / key_id.replace("-", "") / filename
        try:
            stat_data = await path.stat()
            guess_mime, _ = guess_type(filename)
            guess_mime = guess_mime or "application/octet-stream"
            return FileObject(
                purepath,
                guess_mime,
                stat_data.st_size,
                pendulum.from_timestamp(stat_data.st_mtime),
            )
        except FileNotFoundError:
            return None

    async def exists(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        return await self.stat_file(key, key_id, filename, type) is not None

    async def stream_download(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / key / key_id.replace("-", "") / filename
        async with path.open("rb") as f:
            while True:
                chunk = await f.read(1024)
                if not chunk:
                    break
                yield chunk

    async def download(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / key / key_id.replace("-", "") / filename
        async with path.open("rb") as f:
            return await f.read()

    async def delete(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / key / key_id.replace("-", "") / filename
        await path.unlink(missing_ok=True)


ROOT_PATH = Path(__file__).absolute().parent.parent.parent
_LOCALSERVER: LocalStorage = LocalStorage(AsyncPath(ROOT_PATH / "storages"))


def get_local_storage():
    return _LOCALSERVER
