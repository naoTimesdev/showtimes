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

import glob
import inspect
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Optional, overload

import coloredlogs
from dotenv.main import DotEnv

if TYPE_CHECKING:
    from types import ModuleType

__all__ = (
    "RollingFileHandler",
    "setup_logger",
    "load_env",
    "get_env_config",
    "get_logger",
)
ROOT_DIR = Path(__file__).absolute().parent


class RollingFileHandler(RotatingFileHandler):
    """
    A log file handler that follows the same format as RotatingFileHandler,
    but automatically roll over to the next numbering without needing to worry
    about maximum file count or something.

    At startup, we check the last file in the directory and start from there.
    """

    maxBytes: int  # to force mypy to stop complaining????

    def __init__(
        self,
        filename: os.PathLike,
        mode: str = "a",
        maxBytes: int = 0,  # noqa
        backupCount: int = 0,
        encoding: Optional[str] = None,
        delay: bool = False,
    ) -> None:
        self._last_backup_count = 0
        super().__init__(
            filename, mode=mode, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding, delay=delay
        )
        self.maxBytes = maxBytes
        self.backupCount = backupCount
        self._determine_start_count()

    def _determine_start_count(self):
        all_files = glob.glob(self.baseFilename + "*")
        if all_files:
            all_files.sort()
            last_digit = all_files[-1].split(".")[-1]
            if last_digit.isdigit():
                self._last_backup_count = int(last_digit)

    def doRollover(self) -> None:  # noqa: N802
        if self.stream and not self.stream.closed:
            self.stream.close()
        self._last_backup_count += 1
        next_name = "%s.%d" % (self.baseFilename, self._last_backup_count)
        self.rotate(self.baseFilename, next_name)
        if not self.delay:
            self.stream = self._open()


def setup_logger(log_path: Path):
    log_path.parent.mkdir(exist_ok=True)

    file_handler = RollingFileHandler(log_path, maxBytes=5_242_880, backupCount=5, encoding="utf-8")
    logging.basicConfig(
        level=logging.DEBUG,
        handlers=[file_handler],
        format="[%(asctime)s] - (%(name)s)[%(levelname)s](%(funcName)s): %(message)s",  # noqa: E501
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger()
    coloredlogs.install(
        fmt="[%(asctime)s %(hostname)s][%(levelname)s] (%(name)s[%(process)d]): %(funcName)s: %(message)s",
        level=logging.INFO,
        logger=logger,
        stream=sys.stdout,
    )

    # Set default logging for some modules
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.asgi").setLevel(logging.INFO)
    logging.getLogger("websockets").setLevel(logging.WARNING)

    # Set back to the default of INFO even if asyncio's debug mode is enabled.
    logging.getLogger("asyncio").setLevel(logging.INFO)

    return logger


def load_env(env_path: Path):
    """Load an environment file and set it to the environment table

    Returns the environment dict loaded from the dictionary.
    """
    if not env_path.exists():
        return {}
    env = DotEnv(env_path, stream=None, verbose=False, encoding="utf-8", interpolate=True, override=True)
    env.set_as_environment_variables()

    return env.dict()


def get_env_config(is_production: bool = True):
    """Get the configuration from multiple .env file!"""
    current_dir = Path(__file__).absolute().parent
    backend_dir = current_dir.parent
    root_dir = backend_dir.parent
    frontend_dir = root_dir / "frontend"

    # .env file from every directory
    # variant: .env.local, .env.production, .env.development
    # load depends on the current environment (for production and development)

    APP_MODE = os.getenv("APP_MODE", "development")
    is_prod = APP_MODE == "production" or is_production

    env_root = load_env(root_dir / ".env")
    env_front = load_env(frontend_dir / ".env")
    env_back = load_env(backend_dir / ".env")

    # .env.local
    env_root_local = load_env(root_dir / ".env.local")
    env_front_local = load_env(frontend_dir / ".env.local")
    env_back_local = load_env(backend_dir / ".env.local")

    # .env.production
    env_root_prod = load_env(root_dir / ".env.production") if is_prod else {}
    env_front_prod = load_env(frontend_dir / ".env.production") if is_prod else {}
    env_back_prod = load_env(backend_dir / ".env.production") if is_prod else {}

    # .env.development
    env_root_dev = load_env(root_dir / ".env.development") if not is_prod else {}
    env_front_dev = load_env(frontend_dir / ".env.development") if not is_prod else {}
    env_back_dev = load_env(backend_dir / ".env.development") if not is_prod else {}

    # priority: .env.local > .env.production > .env.development > .env
    env_merged = {
        **env_root,
        **env_front,
        **env_back,
        **env_root_local,
        **env_front_local,
        **env_back_local,
        **env_root_prod,
        **env_front_prod,
        **env_back_prod,
        **env_root_dev,
        **env_front_dev,
        **env_back_dev,
    }
    return env_merged


def _inspect_module_name() -> tuple[ModuleType | None, str | None]:
    try:
        stack = inspect.stack()[2]
    except Exception:
        return None, None
    # Get class name
    try:
        class_name = stack[0].f_locals["self"].__class__.__name__
    except Exception:
        class_name = None
    return inspect.getmodule(stack[0]), class_name


def _create_log_name() -> str | None:
    mod, cls_name = _inspect_module_name()
    if mod is None:
        return None
    # Get the path
    file_miss = mod.__file__
    if file_miss is None:
        return None
    mod_path = Path(file_miss)
    relative = mod_path.relative_to(ROOT_DIR).as_posix().split("/")
    # Get the name of the module
    actual_name = []
    for name in relative:
        actual_name.append(name.capitalize().replace(".py", ""))
    mod_name = ".".join(actual_name)
    if cls_name:
        mod_name += f".{cls_name}"
    return mod_name


@overload
def get_logger() -> logging.Logger:
    ...


@overload
def get_logger(name: str) -> logging.Logger:
    ...


def get_logger(name: str | None = None):
    inspect_name = _create_log_name()
    if name is not None:
        return logging.getLogger(name)
    return logging.getLogger(inspect_name)
