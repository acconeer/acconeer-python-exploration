# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import PERCEIVED_WAVELENGTH, AlgoConfigBase, ProcessorBase


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoConfigBase):
    threshold: Optional[float] = attrs.field(default=50.0)


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorResult:
    lp_abs_sweep: npt.NDArray[np.float_]
    angle_sweep: npt.NDArray[np.float_]
    threshold: Optional[float] = attrs.field(default=None)
    rel_time_stamps: npt.NDArray[np.float_]
    distance_history: npt.NDArray[np.float_]
    peak_loc_m: Optional[float] = attrs.field(default=None)


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    estimated_distance: Optional[float]
    prev_peak_loc_m: Optional[float]

    M_TO_MM = 1000
    TIME_HORIZON_S = 5.0

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        self.start_point = sensor_config.start_point
        self.step_length = sensor_config.step_length
        self.num_points = sensor_config.num_points

        self.base_step_length_m = metadata.base_step_length_m

        self.prev_peak_loc_m = None
        self.prev_sweep = np.full(self.num_points, np.nan)

        self.lp_abs_sweep = np.full(self.num_points, np.nan)
        self.lp_coeff = 0.95

        self.sweep_index = 0

        self.threshold = processor_config.threshold

        self.estimated_distance = None

        self.distance_history = np.array([])
        self.time_history = np.array([])

    def process(self, result: a121.Result) -> ProcessorResult:

        frame = result.frame
        sweep = frame.mean(axis=0)
        abs_sweep = np.abs(sweep)

        # initialize filter variables if first sweep
        if self.sweep_index == 0:
            self.prev_sweep = sweep
            self.lp_abs_sweep = abs_sweep

        self.lp_abs_sweep = self.lp_abs_sweep * self.lp_coeff + abs_sweep * (1 - self.lp_coeff)

        if self.threshold < np.max(self.lp_abs_sweep):
            peak_loc_p = np.argmax(self.lp_abs_sweep)
            peak_loc_m = float(
                (self.start_point + peak_loc_p * self.step_length) * self.base_step_length_m
            )
            # Assign prev_peak_loc_m a value if this is the first sweep above the threshold.
            if self.prev_peak_loc_m is None:
                self.prev_peak_loc_m = peak_loc_m

            # Reset estimate if this is the first amplitude above the threshold(estimated_distance
            # is None) or distance between the current and previous peak location is large,
            # indicating new object with greater peak.
            if self.estimated_distance is None or 0.1 < np.abs(peak_loc_m - self.prev_peak_loc_m):
                self.estimated_distance = 0.0

            delta_angle = np.angle(sweep[peak_loc_p] * np.conj(self.prev_sweep[peak_loc_p]))
            delta_dist = PERCEIVED_WAVELENGTH * delta_angle / (2 * np.pi) * self.M_TO_MM
            self.estimated_distance += delta_dist

            assert self.estimated_distance is not None
            self.distance_history = np.append(self.distance_history, self.estimated_distance)
            self.time_history = np.append(self.time_history, result.tick_time)

            # Extract data in desired plot window.
            rel_time = self.time_history - self.time_history[-1]
            plot_idx = np.where(-self.TIME_HORIZON_S < rel_time)
            rel_time_to_plot = rel_time[plot_idx]
            distance_to_plot = self.distance_history[plot_idx]
        else:
            # Reset variables as no peak is detected.
            peak_loc_m = None
            rel_time_to_plot = None
            distance_to_plot = None
            self.prev_peak_loc_m = None
            self.estimated_distance = None
            self.time_history = np.array([])
            self.distance_history = np.array([])

        self.sweep_index += 1
        self.prev_sweep = sweep
        self.prev_peak_loc_m = peak_loc_m

        return ProcessorResult(
            lp_abs_sweep=self.lp_abs_sweep,
            angle_sweep=np.angle(sweep),
            threshold=self.threshold,
            rel_time_stamps=rel_time_to_plot,
            distance_history=distance_to_plot,
            peak_loc_m=peak_loc_m,
        )

    def update_config(self, config: ProcessorConfig) -> None:
        ...


def get_sensor_config() -> a121.SensorConfig:
    return a121.SensorConfig(
        profile=a121.Profile.PROFILE_1,
        start_point=80,
        num_points=40,
        step_length=2,
        receiver_gain=10,
        hwaas=4,
        phase_enhancement=True,
    )
