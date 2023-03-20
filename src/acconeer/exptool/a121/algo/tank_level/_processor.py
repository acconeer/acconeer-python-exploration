# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import enum
import time
from typing import Dict, List, Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase
from acconeer.exptool.a121.algo.distance import DetectorResult


TIME_HISTORY_S = 30
UPDATES_PER_SECOND = 4


class ProcessorLevelStatus(enum.Enum):
    """Status from the processor"""

    IN_RANGE = enum.auto()
    NO_DETECTION = enum.auto()
    OVERFLOW = enum.auto()
    OUT_OF_RANGE = enum.auto()


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    level_and_time_for_plotting: dict[str, npt.NDArray[np.float_]]


@attrs.frozen(kw_only=True)
class ProcessorResult:
    """Processor results"""

    peak_detected: Optional[bool]
    peak_status: Optional[ProcessorLevelStatus]
    filtered_level: Optional[float]
    extra_result: ProcessorExtraResult


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    median_filter_length: int = attrs.field(default=5)
    """Length of the median filter used to stabilize the level result."""
    num_medians_to_average: int = attrs.field(default=5)
    """Number of median values averaged to obtain the level result."""
    tank_range_start_m: float = attrs.field(default=0.030)
    """Minimum detection distance."""
    tank_range_end_m: float = attrs.field(default=0.50)
    """Maximum detection distance."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        return []


class Processor:
    """Tank level indicator processor
    :param processor_config: Processor configuration.
    """

    def __init__(
        self,
        processor_config: ProcessorConfig,
    ):
        self.tank_range_end_m = processor_config.tank_range_end_m
        self.tank_range_start_m = processor_config.tank_range_start_m
        self.median_filter_length = processor_config.median_filter_length
        self.num_medians_to_average = processor_config.num_medians_to_average

        assert self.tank_range_start_m < self.tank_range_end_m

        self.median_counter = 0
        self.mean_counter = 0

        self.level_history = np.full(self.median_filter_length, np.nan)
        self.median_vector = np.full(self.num_medians_to_average, np.nan)

        self.near_edge_status_list: List[Optional[bool]] = []
        self.peak_status_list: List[bool] = []

        self.level_and_time_for_plotting = {
            "time": np.full((TIME_HISTORY_S * UPDATES_PER_SECOND,), np.nan),
            "level": np.full((TIME_HISTORY_S * UPDATES_PER_SECOND,), np.nan),
        }

        self.start_time = time.time()

    def _update_level_history(self, result: DetectorResult) -> None:
        self.median_counter += 1
        assert result.distances is not None

        if len(result.distances) != 0:
            self.level_history = np.append(
                self.level_history, (self.tank_range_end_m - result.distances[0])
            )
        else:
            self.level_history = np.append(self.level_history, np.nan)
        self.level_history = self.level_history[1:]

        self.near_edge_status_list.append(result.near_edge_status)

        if self.median_counter == self.median_filter_length:
            self.median_counter = 0
            # store level in a vector of medians
            self.median_vector = np.append(self.median_vector, np.median(self.level_history))[1:]
            # store peak status from near_edge_status_list to peak_status_list
            self.peak_status_list.append(
                self.near_edge_status_list.count(True) > len(self.near_edge_status_list) / 2
            )
            # clear the edge status list
            self.near_edge_status_list.clear()
            self.mean_counter += 1

    def _update_level_and_time_for_plotting(
        self, filtered_level: Optional[float], rel_time: float
    ) -> None:
        if filtered_level is not None:
            self.level_and_time_for_plotting["time"] = (
                np.append(self.level_and_time_for_plotting["time"], 0) - rel_time
            )[1:]
            self.level_and_time_for_plotting["level"] = (
                np.append(self.level_and_time_for_plotting["level"], filtered_level)
            )[1:]

    def process(self, detector_result: Dict[int, DetectorResult]) -> ProcessorResult:
        # Get the first detector result (single sensor operation).
        (result,) = list(detector_result.values())

        # Assign level status
        # peak_detected: True if a peak is detected by the distance detector in n consecutive
        # frames, where n=median_filter_length.
        # peak_status: Assigned based on the location of the peak in relation to the detection
        # range defined by tank_start and tank_end.
        self._update_level_history(result)

        peak_detected = None
        peak_status = None
        filtered_level = None

        if self.mean_counter == self.num_medians_to_average:
            self.mean_counter = 0
            # assign filtered_level every num_medians_to_average samples
            if np.any(~np.isnan(self.median_vector)):
                filtered_level = np.nanmean(self.median_vector)
            else:
                filtered_level = np.nan

            # assign the detection and peak status
            peak_detected = False
            peak_status = ProcessorLevelStatus.NO_DETECTION

            if ~np.isnan(filtered_level):
                peak_detected = True
                if filtered_level < 0:
                    peak_status = ProcessorLevelStatus.OUT_OF_RANGE
                elif filtered_level > self.tank_range_end_m - self.tank_range_start_m:
                    peak_status = ProcessorLevelStatus.OVERFLOW
                elif (
                    filtered_level <= self.tank_range_end_m - self.tank_range_start_m
                    and self.peak_status_list.count(True) > len(self.peak_status_list) / 2
                ):
                    peak_status = ProcessorLevelStatus.OVERFLOW
                else:
                    peak_status = ProcessorLevelStatus.IN_RANGE
            else:
                if self.peak_status_list.count(True) > len(self.peak_status_list) / 2:
                    peak_status = ProcessorLevelStatus.OVERFLOW

            if peak_status in (ProcessorLevelStatus.OVERFLOW, ProcessorLevelStatus.OUT_OF_RANGE):
                filtered_level = np.nan

            rel_time = time.time() - self.start_time
            if rel_time >= 1 / UPDATES_PER_SECOND:
                self._update_level_and_time_for_plotting(filtered_level, rel_time)
                self.start_time = time.time()

            # clear the peak status list
            self.peak_status_list.clear()

        # extra results for plotting
        extra_result = ProcessorExtraResult(
            level_and_time_for_plotting=self.level_and_time_for_plotting
        )

        return ProcessorResult(
            peak_detected=peak_detected,
            peak_status=peak_status,
            extra_result=extra_result,
            filtered_level=filtered_level,
        )
