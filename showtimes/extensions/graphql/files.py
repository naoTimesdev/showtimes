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
from mimetypes import guess_extension

import magic
from fastapi import UploadFile

from showtimes.controllers.storages import get_local_storage
from showtimes.utils import make_uuid

from .scalars import Upload

__all__ = (
    "InvalidMimeType",
    "get_file_mimetype",
    "handle_image_upload",
)


class InvalidMimeType(ValueError):
    def __init__(self, mime_type: str, expected_mimetype: str):
        self.mime_type = mime_type
        self.expected_mimetype = expected_mimetype
        super().__init__(f"Invalid mime type: {mime_type} (expected: {expected_mimetype})")


@dataclass
class UploadResult:
    filename: str
    extension: str
    file_size: int


async def get_file_mimetype(file: UploadFile):
    # Get current seek position
    loop = asyncio.get_event_loop()
    current_pos = file.file.tell()
    # Seek to start
    await file.seek(0)
    # Read first 2048 bytes
    data = await file.read(2048)
    # Seek back to original position
    await file.seek(current_pos)

    detect = await loop.run_in_executor(None, magic.from_buffer, data, True)
    return detect


async def handle_image_upload(file: Upload, uuid: str, image_type: str) -> UploadResult:
    """
    Handle file upload from GraphQL
    """
    if not isinstance(file, UploadFile):
        raise TypeError("Expected UploadFile, got %r" % file)

    # Handle upload
    stor = get_local_storage()
    mimetype = await get_file_mimetype(file)
    if not mimetype.startswith("image/"):
        raise InvalidMimeType(mimetype, "image/*")

    uuid_gen = str(make_uuid())
    extension = guess_extension(mimetype) or ".bin"
    filename = f"{uuid_gen}{extension}"

    # Upload file
    result = await stor.stream_upload(
        key=image_type,
        key_id=uuid,
        filename=filename,
        data=file,
    )
    if result is None:
        raise RuntimeError("Failed to upload file")
    return UploadResult(filename=uuid_gen, extension=extension, file_size=result.size)
