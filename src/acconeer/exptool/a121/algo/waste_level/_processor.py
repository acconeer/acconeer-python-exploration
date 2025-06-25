# Copyright (c) Acconeer AB, 2024-2025
# All rights reserved

from __future__ import annotations

import collections
from typing import Optional

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    AlgoProcessorConfigBase,
    ProcessorBase,
    get_distances_m,
)


@attributes_doc
@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    _MIN_START_POINT = 32  # Set to avoid direct leakage using profile 1
    _MIN_MEASURABLE_DISTANCE_M = _MIN_START_POINT * APPROX_BASE_STEP_LENGTH_M

    bin_start_m: float = attrs.field(default=0.15)
    """Minimum detection distance from sensor."""
    bin_end_m: float = attrs.field(default=1.00)
    """Maximum detection distance from sensor."""
    threshold: float = attrs.field(default=0.3)
    """Threshold for which the standard deviation of the phase should be below."""
    distance_sequence_n: int = attrs.field(default=4)
    """Number of distance needed in sequence below threshold to be presumed as waste level."""
    median_filter_length: int = attrs.field(default=5)
    """Length of the median filter used to stabilize the level result."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if not self.bin_start_m < self.bin_end_m:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "bin_start_m",
                    "Minimum detection distance must be shorter than maximum detection distance.",
                )
            )

        if config.sensor_config.sweeps_per_frame < 4:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweeps_per_frame",
                    "Sweeps per frame must be > 3.",
                )
            )

        min_measured_point = min(ss.start_point for ss in config.sensor_config.subsweeps)
        max_measured_point = max(
            ss.start_point + (ss.num_points - 1) * ss.step_length
            for ss in config.sensor_config.subsweeps
        )
        min_measured_distance_m = min_measured_point * APPROX_BASE_STEP_LENGTH_M
        max_measured_distance_m = max_measured_point * APPROX_BASE_STEP_LENGTH_M
        measured_range_str = f"{min_measured_distance_m:.2f}-{max_measured_distance_m:.2f}m"

        for subsweep in config.sensor_config.subsweeps:
            if subsweep.start_point < self._MIN_START_POINT:
                validation_results.append(
                    a121.ValidationError(
                        subsweep,
                        "start_point",
                        f"Start point must be greater or equal to {self._MIN_START_POINT}",
                    )
                )

        if self.bin_start_m < self._MIN_MEASURABLE_DISTANCE_M:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "bin_start_m",
                    f"Bin start must be greater or equal to {self._MIN_MEASURABLE_DISTANCE_M} m",
                )
            )

        if not min_measured_distance_m <= self.bin_start_m <= max_measured_distance_m:
            bin_msg = f"Bin start is outside measured range ({measured_range_str})"
            validation_results += [a121.ValidationError(self, "bin_start_m", bin_msg)]

        if not min_measured_distance_m <= self.bin_end_m <= max_measured_distance_m:
            bin_msg = f"Bin end is outside measured range ({measured_range_str})"
            validation_results += [a121.ValidationError(self, "bin_end_m", bin_msg)]

        for (prev_num, prev), (curr_num, curr) in zip(
            enumerate(config.sensor_config.subsweeps, start=1),
            enumerate(config.sensor_config.subsweeps[1:], start=2),
        ):
            if not prev.start_point < curr.start_point:
                msg = (
                    "Start point needs to be larger than the "
                    + f"previous subsweep's start point (at least {prev.start_point + 1})"
                )
                validation_results += [a121.ValidationError(curr, "start_point", msg)]

            prev_end_point = prev.start_point + prev.step_length * (prev.num_points - 1)
            if not prev_end_point < curr.start_point:
                msg = f"Subsweeps {prev_num} and {curr_num} overlap."
                prev_msg = f"{msg} Adjust end point."
                curr_msg = f"{msg} Adjust start point."
                validation_results += [
                    a121.ValidationError(prev, "num_points", prev_msg),
                    a121.ValidationError(prev, "step_length", prev_msg),
                    a121.ValidationError(curr, "start_point", curr_msg),
                ]

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext: ...


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    phase_std: npt.NDArray[np.float64]
    """The standard deviation of the phase from which the distance is detemined."""
    distance_m: Optional[float]
    """Distance from sensor to fill level."""


@attrs.frozen(kw_only=True)
class ProcessorResult:
    level_m: Optional[float]
    """Fill level in the bin in meters."""
    level_percent: Optional[int]
    """Fill level in the bin in percentage."""
    extra_result: ProcessorExtraResult
    """Extra result used for visualization."""


class Processor(ProcessorBase[ProcessorResult]):
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        self.bin_end_m = processor_config.bin_end_m
        self.bin_start_m = processor_config.bin_start_m
        self.median_filter_length = processor_config.median_filter_length
        self.threshold = processor_config.threshold
        self.distance_sequence_n = processor_config.distance_sequence_n

        assert self.bin_start_m < self.bin_end_m

        self.distance_history: collections.deque[float] = collections.deque(
            [], maxlen=self.median_filter_length
        )

        self.distances_m = get_distances_m(sensor_config, metadata)

    def find_distance_m(self, phase_stds: npt.NDArray[np.float64]) -> float:
        stable_phases = phase_stds < self.threshold

        potential_distances = (
            float(self.distances_m[idx])
            for idx in range(len(stable_phases))
            if stable_phases[idx : idx + self.distance_sequence_n].all()
        )

        return next(potential_distances, np.nan)

    def process(self, result: a121.Result) -> ProcessorResult:
        # center the phase distribution around zero
        sweep_sums = np.sum(result.frame, axis=0)
        phases = np.angle(result.frame * np.conj(sweep_sums))

        # calculate standard deviation of the phase at each distance over multiple sweeps
        phase_std = np.std(phases, axis=0)
        distance_m = self.find_distance_m(phase_std)

        self.distance_history.append(distance_m)

        if np.all(np.isnan(list(self.distance_history))):
            level_m = None
            level_percent = None
            filtered_distance = None
        else:
            filtered_distance = float(np.nanmedian(list(self.distance_history)))
            level_m = self.bin_end_m - filtered_distance
            level_percent = int(round(level_m / (self.bin_end_m - self.bin_start_m) * 100, 0))
            if level_percent < 0:
                level_percent = 0

        extra_result = ProcessorExtraResult(phase_std=phase_std, distance_m=filtered_distance)

        return ProcessorResult(
            level_m=level_m,
            level_percent=level_percent,
            extra_result=extra_result,
        )

    def update_config(self, config: ProcessorConfig) -> None: ...


def _load_algo_data(algo_group: h5py.Group) -> ProcessorConfig:
    processor_config = ProcessorConfig.from_json(algo_group["processor_config"][()])
    return processor_config
