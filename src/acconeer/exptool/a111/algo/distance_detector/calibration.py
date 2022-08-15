# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
class DistanceDetectorCalibration(Calibration):
    stationary_clutter_mean: np.ndarray
    stationary_clutter_std: np.ndarray

    def save(self, path: _Path):
        self.validate_path(path, file_extensions=[self.file_extensions()[0]])

        np.savez(
            path,
            mean=self.stationary_clutter_mean,
            std=self.stationary_clutter_std,
        )

    @classmethod
    def load(cls, path: _Path) -> Calibration:
        cls.validate_path(path)

        # Distance Detector saved background as ".npy" in v3
        if Path(path).suffix == ".npy":
            mean_std = np.load(path)
            return DistanceDetectorCalibration(mean_std[0], mean_std[1])
        else:
            with np.load(path) as archive:
                return DistanceDetectorCalibration(
                    archive["mean"],
                    archive["std"],
                )

    @classmethod
    def file_extensions(cls) -> _AcceptedFileExtensions:
        return [
            ("npz", "Numpy data archives (*.npz)"),
            ("npy", "Numpy data files (*.npy)"),
        ]


class DistaceDetectorCalibrationConfiguration(et.configbase.Config):
    pass


class DistaceDetectorCalibrationMapper(CalibrationMapper):
    @classmethod
    def get_updated_calibration_from_configuration(
        cls,
        configuration: DistaceDetectorCalibrationConfiguration,
        calibration: Optional[DistanceDetectorCalibration],
    ) -> DistanceDetectorCalibration:
        if calibration is None:
            raise ValueError("Calibration cannot be None in this context.")

        return calibration

    @classmethod
    def update_config_from_calibration(
        cls,
        configuration: DistaceDetectorCalibrationConfiguration,
        calibration: DistanceDetectorCalibration,
    ) -> None:
        pass
