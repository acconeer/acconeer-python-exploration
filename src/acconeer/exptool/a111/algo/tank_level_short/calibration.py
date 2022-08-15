# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

import acconeer.exptool as et
from acconeer.exptool.a111.algo import (
    Calibration,
    CalibrationMapper,
    _AcceptedFileExtensions,
    _Path,
)


@dataclass(frozen=True)
class EnvelopeCalibration(Calibration):
    background: np.ndarray

    def save(self, path: _Path):
        self.validate_path(path)
        np.save(path, self.background)

    @classmethod
    def load(cls, path: _Path) -> Calibration:
        cls.validate_path(path)
        background = np.load(path)
        return EnvelopeCalibration(background)

    @classmethod
    def file_extensions(cls) -> _AcceptedFileExtensions:
        return [("npy", "Numpy data files (*.npy)")]


class EnvelopeCalibrationConfiguration(et.configbase.Config):
    pass


class EnvelopeCalibrationMapper(CalibrationMapper):
    @classmethod
    def get_updated_calibration_from_configuration(
        cls,
        configuration: EnvelopeCalibrationConfiguration,
        calibration: Optional[EnvelopeCalibration],
    ) -> EnvelopeCalibration:
        if calibration is None:
            raise ValueError("Calibration cannot be None in this context.")

        return calibration

    @classmethod
    def update_config_from_calibration(
        cls,
        configuration: EnvelopeCalibrationConfiguration,
        calibration: EnvelopeCalibration,
    ) -> None:
        pass
