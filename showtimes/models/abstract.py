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

__all__ = ("AttributeDict",)


class AttributeDict(dict):
    """An attribute-based dictionary."""

    def __init__(self, *args, **kwargs):
        def from_nested_dict(data):
            """Construct nested AttributeDict from nested dictionaries."""
            if not isinstance(data, (dict, list, tuple)):
                return data
            else:
                if isinstance(data, dict):
                    return AttributeDict({k: from_nested_dict(data[k]) for k in data.keys()})
                else:
                    return [from_nested_dict(item) for item in data]

        super(AttributeDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

        for key in self.keys():
            self[key] = from_nested_dict(self[key])

    def __repr__(self):
        concat_data = []
        for key in self.keys():
            concat_data.append(f"{key}={self[key]!r}")
        return f"<AttributeDict {' '.join(concat_data)}>"
