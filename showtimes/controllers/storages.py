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

import asyncio
from dataclasses import dataclass
from mimetypes import guess_type
from pathlib import Path
from typing import IO, Any, AsyncIterator, Coroutine, Optional, Protocol, Union, cast

import pendulum
from aiobotocore.session import AioSession as BotocoreSession
from aiopath import AsyncPath
from pendulum.datetime import DateTime
from types_aiobotocore_s3 import S3Client

__all__ = (
    "FileObject",
    "LocalStorage",
    "get_local_storage",
    "get_s3_storage",
    "init_s3_storage",
    "get_storage",
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


class S3Storage:
    _client: Optional[S3Client]

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: Optional[str],
        *,
        host: Optional[str] = None,
    ) -> None:
        self._session = BotocoreSession()
        self._client: Optional[S3Client] = None

        self.__key = access_key
        self.__bucket = bucket
        self.__secret = secret_key
        self.__region = region
        self.__host = host

    async def start(self):
        if self._client is None:
            self._client = self._session.create_client(
                "s3",
                region_name=self.__region,
                endpoint_url=self.__host,
                aws_access_key_id=self.__key,
                aws_secret_access_key=self.__secret,
            )

    async def close(self):
        if self._client is not None:
            await self._client.close()

    async def stream_upload(self, key: str, key_id: str, filename: str, data: StreamableData, type: str = "images"):
        await self.start()
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            client: S3Client
            await client.put_object(Bucket=self.__bucket, Key=path, Body=cast(IO[bytes], data))
            return await self.stat_file(key, key_id, filename, type)

    async def stat_file(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            try:
                resp = await client.get_object_attributes(
                    Bucket=self.__bucket,
                    Key=path,
                    ObjectAttributes=["ObjectSize"],
                )
            except client.exceptions.NoSuchKey:
                return None
            size = resp["ObjectSize"]
            last_mod = resp["LastModified"]
            guess_mime, _ = guess_type(filename)
            guess_mime = guess_mime or "application/octet-stream"
            return FileObject(
                path,
                guess_mime,
                size,
                pendulum.instance(last_mod),
            )

    async def exists(self, key: str, key_id: str, filename: str, type: str = "images"):
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            try:
                resp = await client.get_object_attributes(
                    Bucket=self.__bucket,
                    Key=path,
                    ObjectAttributes=["ObjectSize"],
                )
                if resp["ObjectSize"] > 0:
                    return True
                return False
            except client.exceptions.NoSuchKey:
                return False

    async def stream_download(self, key: str, key_id: str, filename: str, type: str = "images") -> AsyncIterator[bytes]:
        await self.start()
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            try:
                resp = await client.get_object(Bucket=self.__bucket, Key=path)
                async with resp["Body"] as stream:
                    yield await stream.read(1024)
            except client.exceptions.NoSuchKey:
                raise FileNotFoundError

    async def download(self, key: str, key_id: str, filename: str, type: str = "images") -> Coroutine[Any, Any, bytes]:
        await self.start()
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            try:
                resp = await client.get_object(Bucket=self.__bucket, Key=path)
                async with resp["Body"] as stream:
                    return await stream.read()
            except client.exceptions.NoSuchKey:
                raise FileNotFoundError

    async def delete(self, key: str, key_id: str, filename: str, type: str = "images"):
        await self.start()
        path = f"{type}/{key}/{key_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        async with self._client as client:
            try:
                await client.delete_object(Bucket=self.__bucket, Key=path)
            except client.exceptions.NoSuchKey:
                return


ROOT_PATH = Path(__file__).absolute().parent.parent.parent
_LOCALSERVER: LocalStorage = LocalStorage(AsyncPath(ROOT_PATH / "storages"))
_GLOBAL_S3SERVER: Optional[S3Storage] = None


def get_local_storage():
    return _LOCALSERVER


def get_s3_storage():
    global _GLOBAL_S3SERVER

    if _GLOBAL_S3SERVER is None:
        raise ValueError("S3 storage not created, call init_s3_storage first")

    return _GLOBAL_S3SERVER


async def init_s3_storage(
    bucket: str,
    access_key: str,
    secret_key: str,
    region: Optional[str],
    *,
    host: Optional[str] = None,
):
    global _GLOBAL_S3SERVER

    stor = S3Storage(bucket, access_key, secret_key, region, host=host)
    await stor.start()
    _GLOBAL_S3SERVER = stor


def get_storage():
    if _GLOBAL_S3SERVER is not None:
        return _GLOBAL_S3SERVER
    return _LOCALSERVER
