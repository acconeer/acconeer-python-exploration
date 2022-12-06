# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import PERCEIVED_WAVELENGTH, AlgoProcessorConfigBase, ProcessorBase


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    threshold: Optional[float] = attrs.field(default=50.0)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.sensor_config.sweep_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweep_rate",
                    "Must be set",
                )
            )

        if not config.sensor_config.double_buffering:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "double_buffering",
                    "Must be enabled",
                )
            )

        if not config.sensor_config.continuous_sweep_mode:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "continuous_sweep_mode",
                    "Must be enabled",
                )
            )

        return validation_results


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
    LP_COEFF = 0.75

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:

        processor_config.validate(sensor_config)

        # Should never happen, checked in validate
        assert sensor_config.sweep_rate is not None

        self.start_point = sensor_config.start_point
        self.step_length = sensor_config.step_length
        self.num_points = sensor_config.num_points

        self.base_step_length_m = metadata.base_step_length_m

        self.prev_peak_loc_m = None

        self.lp_abs_sweep = np.full(self.num_points, np.nan)

        self.sweep_index = 0

        self.threshold = processor_config.threshold

        self.max_num_points_to_plot = int(sensor_config.sweep_rate * self.TIME_HORIZON_S)
        self.distance_history: npt.NDArray[np.float_] = np.array([])

    def process(self, result: a121.Result) -> ProcessorResult:

        frame = result.frame
        abs_sweep = np.mean(np.abs(frame), axis=0)

        # initialize filter variables if first sweep
        if self.sweep_index == 0:
            self.lp_abs_sweep = abs_sweep

        self.lp_abs_sweep = self.lp_abs_sweep * self.LP_COEFF + abs_sweep * (1 - self.LP_COEFF)

        if self.threshold < np.max(self.lp_abs_sweep):
            peak_loc_p = np.argmax(self.lp_abs_sweep)
            peak_loc_m = float(
                (self.start_point + peak_loc_p * self.step_length) * self.base_step_length_m
            )
            # Assign prev_peak_loc_m a value if this is the first sweep above the threshold.
            if self.prev_peak_loc_m is None:
                self.prev_peak_loc_m = peak_loc_m

            # Reset estimate if this is the first amplitude above the threshold(length of
            # distance_history is 0) or distance between the current and previous peak location
            # is large, indicating new object with greater peak.
            if self.distance_history.shape[0] == 0 or 0.1 < np.abs(
                peak_loc_m - self.prev_peak_loc_m
            ):
                self.distance_history = np.array([0.0])

            delta_angles = np.diff(np.unwrap(np.angle(frame[:, peak_loc_p])))
            delta_dists = PERCEIVED_WAVELENGTH * delta_angles / (2 * np.pi) * self.M_TO_MM

            # Append the new distances to the previous distances. Offset the new values with
            # the last value in the existing series for a smooth transition.
            self.distance_history = np.append(
                self.distance_history, self.distance_history[-1] + np.cumsum(delta_dists)
            )

            # Extract data in desired plot window.
            distance_to_plot = self.distance_history[-self.max_num_points_to_plot :]
            time_series_length = distance_to_plot.shape[0]
            rel_time_to_plot = np.linspace(
                -self.TIME_HORIZON_S * time_series_length / self.max_num_points_to_plot,
                0,
                time_series_length,
            )
        else:
            # Reset variables as no peak is detected.
            peak_loc_m = None
            distance_to_plot = np.array([])
            self.prev_peak_loc_m = None
            rel_time_to_plot = np.array([])
            self.distance_history = np.array([])

        self.sweep_index += 1
        self.prev_peak_loc_m = peak_loc_m

        return ProcessorResult(
            lp_abs_sweep=self.lp_abs_sweep,
            angle_sweep=np.angle(np.mean(frame, axis=0)),
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
        continuous_sweep_mode=True,
        sweeps_per_frame=25,
        sweep_rate=500,
        double_buffering=True,
        inter_sweep_idle_state=a121.IdleState.READY,
        inter_frame_idle_state=a121.IdleState.READY,
    )
