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
from typing import (
    IO,
    AsyncIterator,
    Awaitable,
    Optional,
    Protocol,
    Type,
    TypeAlias,
    TypeVar,
    Union,
    cast,
    overload,
)

import pendulum
from aiobotocore.session import AioSession as BotocoreSession
from aiopath import AsyncPath
from pendulum.datetime import DateTime
from types_aiobotocore_s3 import S3Client

from showtimes.errors import ShowtimesControllerUninitializedError
from showtimes.tooling import get_logger

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

    def read(self, size: int = -1) -> bytes:
        ...

    @overload
    def seek(self, offset: int, /) -> int:
        ...

    @overload
    def seek(self, offset: int, whence: int, /) -> int:
        ...

    def seek(self, offset: int, whence: int = ..., /) -> int:
        ...


async def _run_in_executor(func, *args, **kwargs):
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    kwargs_args = [val for val in kwargs.values()]
    return await asyncio.get_event_loop().run_in_executor(None, func, *args, *kwargs_args)


_StorT = TypeVar("_StorT", bound="Storage")
T = TypeVar("T")
MaybeFile: TypeAlias = Optional[FileObject]


# Base class
class Storage(Protocol):
    """
    Base class for all storage implementation.
    """

    async def start(self) -> Awaitable[None]:
        """
        Start the storage connection.

        Any connection can be made here.
        """
        ...

    def close(self) -> None:
        """
        Close the storage connection.

        Connection cleanup can be made here.
        """
        ...

    async def stat_file(
        self: Type[_StorT],
        base_key: str,
        parent_id: str,
        filename: str,
        type: str = ...,
    ) -> MaybeFile:
        """
        (Async) Get file information.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        MaybeFile
            The file information if exists, else None.
        """
        ...

    async def exists(
        self,
        base_key: str,
        parent_id: str,
        filename: str,
        type: str = ...,
    ) -> bool:
        """
        (Async) Check if the file exists.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        This calls :method:`stat_file` under the hood.

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        bool
            True if exists, else False.
        """
        ...

    async def stream_upload(
        self,
        base_key: str,
        parent_id: str,
        filename: str,
        data: StreamableData,
        type: str = ...,
    ) -> MaybeFile:
        """
        (Async) Upload a file, using data stream.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        data: :class:`StreamableData`
            A class that implements :class:`StreamableData` protocol. Should contains
            `.read()` and `.seek()` method, both can be async or not.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        MaybeFile
            The uploaded file information, if success, else None.
        """
        ...

    async def stream_download(
        self,
        base_key: str,
        parent_id: str,
        filename: str,
        type: str = ...,
    ) -> AsyncIterator[bytes]:
        """
        (Async) Download a file, using data stream.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        AsyncIterator[bytes]
            The file data stream, can be used in `async for` loop.
        """
        ...

    async def download(
        self,
        base_key: str,
        parent_id: str,
        filename: str,
        type: str = ...,
    ) -> bytes:
        """
        (Async) Download a file.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        bytes
            The file data.
        """
        ...

    async def delete(
        self,
        base_key: str,
        parent_id: str,
        filename: str,
        type: str = ...,
    ) -> None:
        """
        (Async) Delete a file.

        The path that will be accessed are like this:
        - `{type}/{base_key}}/{parent_id}/{filename}`

        Parameters
        ----------
        base_key: :class:`str`
            The base key or path for the file.
        parent_id: :class:`str`
            The parent ID for the file. (User or Group ID or something similar)
        filename: :class:`str`
            The filename for the file.
        type: :class:`str`
            The type of the file that we want to access.
            Basically the base folder for the storage.

        Returns
        -------
        None
            Nothing.
        """
        ...


class LocalStorage(Storage):
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

    async def stat_file(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        purepath = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        path = self._root / type / base_key / parent_id.replace("-", "") / filename
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

    async def exists(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        return await self.stat_file(base_key, parent_id, filename, type) is not None

    async def stream_upload(
        self, base_key: str, parent_id: str, filename: str, data: StreamableData, type: str = "images"
    ):
        await self.start()
        path = self._root / type / base_key / parent_id.replace("-", "") / filename
        await path.parent.mkdir(parents=True, exist_ok=True)
        await _run_in_executor(data.seek, 0)
        async with path.open("wb") as f:
            read = await _run_in_executor(data.read, 1024)
            if not read:
                return
            await f.write(read)
        return await self.stat_file(base_key, parent_id, filename, type)

    async def stream_download(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / base_key / parent_id.replace("-", "") / filename
        async with path.open("rb") as f:
            while True:
                chunk = await f.read(1024)
                if not chunk:
                    break
                yield chunk

    async def download(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / base_key / parent_id.replace("-", "") / filename
        async with path.open("rb") as f:
            return await f.read()

    async def delete(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        path = self._root / type / base_key / parent_id.replace("-", "") / filename
        await path.unlink(missing_ok=True)


class S3Storage(Storage):
    _client: Optional[S3Client]

    def __init__(
        self,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: Optional[str],
        *,
        endpoint: Optional[str] = None,
    ) -> None:
        self._session = BotocoreSession()
        self._client: Optional[S3Client] = None
        self._logger = get_logger("Showtimes.Storage.S3Storage")

        self.__key = access_key
        self.__bucket = bucket
        self.__secret = secret_key
        self.__region = region
        self.__endpoint = endpoint

    async def start(self):
        if self._client is None:
            self._client = await self._session.create_client(
                "s3",  # type: ignore
                region_name=self.__region,
                endpoint_url=self.__endpoint,
                aws_access_key_id=self.__key,
                aws_secret_access_key=self.__secret,
            ).__aenter__()
            await self._test()

    async def _test(self):
        if self._client is None:
            raise RuntimeError("Client not started")

        try:
            self._logger.info("Testing connection to S3 server...")
            results = await self._client.list_objects_v2(Bucket=self.__bucket)
            resp_meta = results["ResponseMetadata"]
            status_code = resp_meta["HTTPStatusCode"]
            if status_code != 200:
                raise RuntimeError("Connection to S3 server failed!")
            self._logger.info("Connection to S3 server successful!")
        except self._client.exceptions.ClientError as exc:
            self._logger.error("Connection to S3 server failed!", exc_info=exc)
            raise RuntimeError("Connection to S3 server failed!") from exc

    async def close(self):
        if self._client is not None:
            await self._client.close()

    async def stat_file(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        try:
            resp = await self._client.head_object(
                Bucket=self.__bucket,
                Key=path,
            )
        except self._client.exceptions.NoSuchKey:
            return None
        size = resp["ContentLength"]
        last_mod = resp["LastModified"]
        guess_mime, _ = guess_type(filename)
        guess_mime = guess_mime or "application/octet-stream"
        return FileObject(
            path,
            guess_mime,
            size,
            pendulum.instance(last_mod),
        )

    async def exists(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        try:
            resp = await self._client.get_object_attributes(
                Bucket=self.__bucket,
                Key=path,
                ObjectAttributes=["ObjectSize"],
            )
            if resp["ObjectSize"] > 0:
                return True
            return False
        except self._client.exceptions.NoSuchKey:
            return False

    async def stream_upload(
        self, base_key: str, parent_id: str, filename: str, data: StreamableData, type: str = "images"
    ):
        await self.start()
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        await self._client.put_object(Bucket=self.__bucket, Key=path, Body=cast(IO[bytes], data))
        return await self.stat_file(base_key, parent_id, filename, type)

    async def stream_download(
        self, base_key: str, parent_id: str, filename: str, type: str = "images"
    ) -> AsyncIterator[bytes]:
        await self.start()
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        try:
            resp = await self._client.get_object(Bucket=self.__bucket, Key=path)
            async with resp["Body"] as stream:
                yield await stream.read(1024)
        except self._client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError from exc

    async def download(self, base_key: str, parent_id: str, filename: str, type: str = "images") -> bytes:
        await self.start()
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        try:
            resp = await self._client.get_object(Bucket=self.__bucket, Key=path)
            async with resp["Body"] as stream:
                return await stream.read()
        except self._client.exceptions.NoSuchKey as exc:
            raise FileNotFoundError from exc

    async def delete(self, base_key: str, parent_id: str, filename: str, type: str = "images"):
        await self.start()
        path = f"{type}/{base_key}/{parent_id.replace('-', '')}/{filename}"
        if self._client is None:
            raise RuntimeError("Client not started")
        try:
            await self._client.delete_object(Bucket=self.__bucket, Key=path)
        except self._client.exceptions.NoSuchKey:
            return


ROOT_PATH = Path(__file__).absolute().parent.parent.parent
_LOCALSERVER: LocalStorage = LocalStorage(AsyncPath(ROOT_PATH / "storages"))
_GLOBAL_S3SERVER: Optional[S3Storage] = None


def get_local_storage() -> LocalStorage:
    return _LOCALSERVER


def get_s3_storage() -> S3Storage:
    global _GLOBAL_S3SERVER

    if _GLOBAL_S3SERVER is None:
        raise ShowtimesControllerUninitializedError("S3 Storage")

    return _GLOBAL_S3SERVER


async def init_s3_storage(
    bucket: str,
    access_key: str,
    secret_key: str,
    region: Optional[str],
    *,
    endpoint: Optional[str] = None,
):
    global _GLOBAL_S3SERVER

    stor = S3Storage(bucket, access_key, secret_key, region, endpoint=endpoint)
    await stor.start()
    _GLOBAL_S3SERVER = stor


def get_storage() -> Storage:
    if _GLOBAL_S3SERVER is not None:
        return _GLOBAL_S3SERVER
    return _LOCALSERVER
