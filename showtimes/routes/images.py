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

from mimetypes import guess_type
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.datastructures import Default
from fastapi.responses import StreamingResponse

from showtimes.controllers.storages import get_storage

__all__ = ("router",)
router = APIRouter(
    prefix="/images",
    default_response_class=Default(StreamingResponse),
    tags=["Images"],
)


def _modern_filetype_guess(filename: str):
    files = filename.rsplit(".", 1)
    if len(files) == 1:
        return "application/octet-stream"

    _, ext = files
    ext = ext.lower()
    if ext in ["jxl"]:
        return "image/jxl"
    elif ext in ["webp"]:
        return "image/webp"
    elif ext in ["heic", "heics", "heif", "heifs"]:
        end_s = "-sequence" if ext.endswith("s") else ""
        ext_act = ext[:-1] if ext.endswith("s") else ext
        return f"image/{ext_act}{end_s}"
    elif ext in ["avif", "avci", "avcs"]:
        return "image/avif"

    return "application/octet-stream"


@router.get("/{type}/{id}/{filename}", description="Get image from storage with only key ID")
async def images_routing_no_parent_get(type: str, id: str, filename: str):
    storage = get_storage()

    async def iterator_stream():
        try:
            async for chunk in storage.stream_download(base_key=id, parent_id=None, filename=filename, type=type):
                yield chunk
        except FileNotFoundError as exc:
            raise HTTPException(404, "Image not found") from exc

    mime_type, _ = guess_type(filename)
    mime_type = mime_type or _modern_filetype_guess(filename)

    return StreamingResponse(iterator_stream(), media_type=mime_type)


@router.get("/{type}/{parent}/{id}/{filename}", description="Get image from storage with parent ID and key ID")
async def images_routing_with_parent_get(type: str, parent: str, id: str, filename: str):
    storage = get_storage()
    try:
        streamer = storage.stream_download(base_key=parent, parent_id=id, filename=filename, type=type)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Image not found") from exc

    async def iterator_stream(stream_input: AsyncGenerator[bytes, None]):
        async for chunk in stream_input:
            yield chunk

    mime_type, _ = guess_type(filename)
    mime_type = mime_type or _modern_filetype_guess(filename)

    return StreamingResponse(iterator_stream(streamer), media_type=mime_type)
