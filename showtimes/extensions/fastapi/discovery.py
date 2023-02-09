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

# Autodiscover all routes

from __future__ import annotations

import logging
from importlib import import_module, util
from pathlib import Path
from typing import Union

from fastapi import APIRouter, FastAPI

__all__ = ("discover_routes",)

logger = logging.getLogger("Showtimes.Extensions.FastAPI.Discovery")


def discover_routes(
    app_or_router: Union[APIRouter, FastAPI],
    route_path: Path,
    recursive: bool = False,
    **router_kwargs,
):
    mod = app_or_router.__module__
    _imported = set()
    routes_iter = route_path.glob("*.py") if not recursive else route_path.rglob("*.py")
    for route in routes_iter:
        if route.name == "__init__.py":
            continue
        route_dot = "showtimes.routes." + route.relative_to(route_path).with_suffix("").as_posix().replace("/", ".")
        if route_dot not in _imported:
            module = import_module(route_dot, mod)
            _imported.add(route_dot)
        logger.info(f"Loading route: {route.stem}")
        spec = util.spec_from_file_location(route_dot, route)
        if spec is None:
            logger.warning(f"Failed to load route {route.name}")
            continue
        if spec.loader is None:
            logger.warning(f"Unable to specify module loader for {route.name}")
            continue
        module = util.module_from_spec(spec)
        spec.loader.exec_module(module)
        router_code = getattr(module, "router", None)
        if router_code is None:
            logger.warning(f'Failed to find "router" variable in {route.stem}')
            continue
        if not isinstance(router_code, APIRouter):
            logger.warning(f'"router" variable in {route.stem} is not an fastapi.APIRouter')
            continue
        logger.info(f'Attaching route "{route.stem}"')
        app_or_router.include_router(router_code, **router_kwargs)
