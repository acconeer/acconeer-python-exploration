# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import itertools
from typing import Optional

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase, ProcessorBase, get_distances_m


@attributes_doc
@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
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

        for (subssweep_a_idx, subsweep_a), (subssweep_b_idx, subsweep_b) in itertools.combinations(
            enumerate(config.sensor_config.subsweeps, start=1), 2
        ):
            if (
                subsweep_a.start_point + subsweep_a.step_length * (subsweep_a.num_points - 1)
                > subsweep_b.start_point
            ):
                validation_results.append(
                    a121.ValidationError(
                        subsweep_a,
                        "num_points",
                        f"Range overlap between subsweeps is not supported. Overlaps with subsweep {subssweep_b_idx}.",
                    )
                )
                validation_results.append(
                    a121.ValidationError(
                        subsweep_b,
                        "start_point",
                        f"Range overlap between subsweep is not supported. Overlaps with subsweep {subssweep_a_idx}.",
                    )
                )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    phase_std: npt.NDArray[np.float_]
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

        self.distance_history = np.full(self.median_filter_length, np.nan)

        self.distances_m = get_distances_m(sensor_config, metadata)

    def find_distance_m(self, phase_stds: npt.NDArray[np.float_]) -> Optional[float]:
        distance_idxs = np.argwhere(phase_stds < self.threshold)
        stable_phases = phase_stds < self.threshold

        distance_found = False
        distance_m = np.nan
        i = 0
        while not distance_found and i < (distance_idxs.shape[0] - self.distance_sequence_n - 1):
            idx = distance_idxs[i][0]
            if np.all(stable_phases[idx : idx + self.distance_sequence_n]):
                distance_found = True
                distance_m = float(self.distances_m[idx])
            i += 1

        return distance_m

    def process(self, result: a121.Result) -> ProcessorResult:
        # center the phase distribution around zero
        sweep_sums = np.sum(result.frame, axis=0)

        if np.all(sweep_sums) > 0:  # check to not set all phases zero
            phases = np.angle(result.frame * np.conj(sweep_sums))
        else:
            phases = np.zeros_like(result.frame)
            for distance, sweep_sum in enumerate(sweep_sums):
                if sweep_sum == 0:
                    sweep_phases = np.angle(result.frame[:, distance])
                else:
                    sweep_phases = np.angle(result.frame[:, distance] * np.conj(sweep_sum))
                phases[:, distance] = sweep_phases

        # calculate standard deviation of the phase at each distance over multiple sweeps
        phase_std = np.std(phases, axis=0)

        if np.any(phase_std < self.threshold):
            distance_m = self.find_distance_m(phase_std)
        else:
            distance_m = np.nan

        self.distance_history = np.roll(self.distance_history, -1)
        self.distance_history[-1] = distance_m

        if np.all(np.isnan(self.distance_history)):
            level_m = None
            level_percent = None
            filtered_distance = None
        else:
            filtered_distance = np.nanmedian(self.distance_history)
            level_m = self.bin_end_m - filtered_distance
            level_percent = int(
                np.maximum(np.around(level_m / (self.bin_end_m - self.bin_start_m) * 100), 0)
            )

        extra_result = ProcessorExtraResult(phase_std=phase_std, distance_m=filtered_distance)

        return ProcessorResult(
            level_m=level_m,
            level_percent=level_percent,
            extra_result=extra_result,
        )

    def update_config(self, config: ProcessorConfig) -> None:
        ...


def _load_algo_data(algo_group: h5py.Group) -> ProcessorConfig:
    processor_config = ProcessorConfig.from_json(algo_group["processor_config"][()])
    return processor_config
