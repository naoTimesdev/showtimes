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

# Adapted from: https://github.com/kostyachum/python-markdown-plain-text

from __future__ import annotations

from typing import Any, Callable
from xml.etree.ElementTree import Comment, Element, ElementTree, ProcessingInstruction

from markdown import Extension
from markdown.core import Markdown

__all__ = ("PlainTextExtension",)


def _serialize_text(writer: Callable[[Any], None], element: Element):
    tag = element.tag
    text = element.text
    if tag is Comment:
        pass
    elif tag is ProcessingInstruction:
        pass
    elif tag is None:
        if text:
            writer(text)
        for e in element:
            _serialize_text(writer, e)
    else:
        if text:
            if tag.lower() not in ["script", "style"]:
                writer(text)
        for e in element:
            _serialize_text(writer, e)

    if element.tail:
        writer(element.tail)


def _writer(root: Element):
    if root is None:
        raise ValueError("Root element is None")

    data = []
    writer = data.append
    _serialize_text(writer, root)
    return "".join(data)


def _md_serializer(element: Element):
    return _writer(ElementTree(element).getroot())


class PlainTextExtension(Extension):
    def extendMarkdown(self, md: Markdown) -> None:  # noqa: N802
        md.serializer = _md_serializer
        md.stripTopLevelTags = False  # type: ignore

        md.set_output_format = lambda x: x  # type: ignore
