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
from typing import cast

import magic
from fastapi import UploadFile

from showtimes.controllers.storages import get_storage
from showtimes.models.database import ImageMetadata
from showtimes.utils import make_uuid

from .scalars import Upload

__all__ = (
    "InvalidMimeType",
    "get_file_mimetype",
    "handle_image_upload",
    "delete_image_upload",
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


def _mmagic_modern_img_format(magic: bytes):
    # For older versions of libmagic
    # AVIF/HEIF/HEIC
    if magic[4:8] == b"ftyp":
        if magic[8:12] in (b"heic", b"heix", b"heis" b"heim"):
            return "image/heic"
        if magic[8:12] in (b"hevc", b"hevx", b"hevs" b"hevm"):
            return "image/heic-sequence"
        if magic[8:12] in (b"avif"):
            return "image/avif"
    # JXL
    # FF 0A BA 21 E8 BC 80 84 E2 42 00 12 88
    if magic[:2] == b"\xff\x0a" or magic[:12] == b"\x00\x00\x00\x0c\x4a\x58\x4c\x20\x0d\x0a\x87\x0a":
        return "image/jxl"
    # WEBP
    if magic[:4] == b"RIFF" and magic[8:12] == b"WEBP":
        return "image/webp"
    return None


async def get_file_mimetype(file: UploadFile) -> str:
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


async def handle_image_upload(
    file: Upload, base_key: str, parent_id: str | None = None, filename: str | None = None, *, type: str
) -> UploadResult:
    """
    Handle file upload from GraphQL
    """
    if not isinstance(file, UploadFile):
        raise TypeError("Expected UploadFile, got %r" % file)

    file_cast = cast(UploadFile, file)
    # Handle upload
    stor = get_storage()
    mimetype = await get_file_mimetype(file_cast)
    if mimetype == "application/octet-stream":
        magic_bits = await file_cast.read(16)
        # Special way to detect AVIF/HEIF/HEIC/JXL
        # Seems like libmagic doesn't detect them properly
        mimetype = _mmagic_modern_img_format(magic_bits) or mimetype
    if not mimetype.startswith("image/"):
        raise InvalidMimeType(mimetype, "image/*")

    uuid_gen = filename or str(make_uuid())
    extension = guess_extension(mimetype) or ".bin"
    actual_filename = f"{uuid_gen}{extension}"

    # Seek back to start
    await file_cast.seek(0)

    # Upload file
    result = await stor.stream_upload(
        base_key=base_key,
        parent_id=parent_id,
        filename=actual_filename,
        data=file,
        type=type,
    )
    if result is None:
        raise RuntimeError("Failed to upload file")
    return UploadResult(filename=actual_filename, extension=extension, file_size=result.size)


async def delete_image_upload(image_meta: ImageMetadata):
    """
    Delete image upload from storage
    """
    stor = get_storage()
    await stor.delete(image_meta.key, image_meta.parent, image_meta.filename, image_meta.type)
