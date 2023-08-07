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
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from showtimes.tooling import get_logger

__all__ = (
    "PredictionInput",
    "PredictionModels",
    "PredictionType",
    "get_prediction_system",
    "load_prediction_models",
)
logger = get_logger("Showtimes.Controllers.Prediction")


class PredictionType(str, Enum):
    NEXT = "next"
    OVERALL = "overall"


@dataclass
class PredictionInput:
    id: str
    episode_count: int
    project_type: str
    episode: int | None = None


class PredictionModels:
    def __init__(self, *, loop: asyncio.AbstractEventLoop | None = None) -> None:
        self._available = False
        self._loop = loop or asyncio.get_event_loop()

        self._model_non_next: RandomForestRegressor | None = None
        self._model_non_overall: RandomForestRegressor | None = None
        self._model_sim_next: RandomForestRegressor | None = None
        self._model_sim_overall: RandomForestRegressor | None = None

    async def load(self):
        if self._available:
            return

        DATASET_PATH = Path(__file__).parent.parent.parent / "datasets"

        model_sim_next = DATASET_PATH / "model_with_simulated_next.shmodel"
        model_sim_overall = DATASET_PATH / "model_with_simulated_overall.shmodel"
        model_non_next = DATASET_PATH / "model_non_simulated_next.shmodel"
        model_non_overall = DATASET_PATH / "model_non_simulated_overall.shmodel"

        self._model_sim_next = await self._loop.run_in_executor(None, joblib.load, model_sim_next)
        self._model_sim_overall = await self._loop.run_in_executor(None, joblib.load, model_sim_overall)
        self._model_non_next = await self._loop.run_in_executor(None, joblib.load, model_non_next)
        self._model_non_overall = await self._loop.run_in_executor(None, joblib.load, model_non_overall)

        self._available = True

    def _str_to_intsafe(self, strdata: str):
        data = int.from_bytes(strdata.encode(), "little")
        # Fit to float32
        return data % 2**32

    async def predict(self, data: PredictionInput, *, type: PredictionType, use_simulated: bool = False) -> int | None:
        """Do a prediction

        Parameters
        ----------
        model : PredictionType
            _description_
        use_simulated : bool, optional
            _description_, by default False
        """

        if not self._available:
            raise RuntimeError("Models are not loaded yet")

        if type == PredictionType.NEXT:
            model = self._model_sim_next if use_simulated else self._model_non_next
        elif type == PredictionType.OVERALL:
            model = self._model_sim_overall if use_simulated else self._model_non_overall
        else:
            raise ValueError(f"Invalid prediction type: {type}")

        if model is None:
            raise RuntimeError(f"Selected model {type.name}{'-SIMULATED' if use_simulated else ''} is not loaded yet")

        input_json = {
            "episode_count": data.episode_count,
            "project_type": self._str_to_intsafe(data.project_type),
        }
        if isinstance(data.episode, int):
            input_json["episode"] = data.episode

        logger.debug(f"Doing prediction with {type} (simulated? {use_simulated}) | {data}")

        df = pd.DataFrame([input_json])
        df["project_type"] = df["project_type"].astype("category")

        result = await self._loop.run_in_executor(None, model.predict, df)

        # Cleanup the result
        days = result[0]
        logger.debug(f"Raw prediction result: {days}")
        days_ceil = math.ceil(days)
        if days == 0.0:
            return None
        # If we have minus, convert it to plus but make sure to limit it to only if it 10 days max
        if days < 0 and days >= -10:
            return math.floor(days) * -1
        return days_ceil


_PREDICTION_SYSTEM = PredictionModels()


async def load_prediction_models():
    global _PREDICTION_SYSTEM
    await _PREDICTION_SYSTEM.load()


def get_prediction_system():
    global _PREDICTION_SYSTEM

    return _PREDICTION_SYSTEM
