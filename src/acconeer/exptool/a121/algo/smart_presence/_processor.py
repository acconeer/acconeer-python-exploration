# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase
from acconeer.exptool.a121.algo.presence import DetectorConfig, DetectorMetadata, DetectorResult


@attrs.frozen(kw_only=True)
class ProcessorResult:
    """Processor result"""

    zone_limits: npt.NDArray[np.float_] = attrs.field()
    max_presence_zone: Optional[int] = attrs.field()
    total_zone_detections: npt.NDArray[np.int_] = attrs.field()
    inter_zone_detections: npt.NDArray[np.int_] = attrs.field()
    max_inter_zone: Optional[int] = attrs.field()
    intra_zone_detections: npt.NDArray[np.int_] = attrs.field()
    max_intra_zone: Optional[int] = attrs.field()


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    num_zones: int = attrs.field(default=3)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:

        return []


class Processor:
    """Smart presence processor
    :param processor_config: Processor configuration.
    """

    max_inter_zone: Optional[int]
    max_intra_zone: Optional[int]

    def __init__(
        self,
        processor_config: ProcessorConfig,
        detector_config: DetectorConfig,
        session_config: a121.SessionConfig,
        detector_metadata: DetectorMetadata,
    ):
        num_points = session_config.sensor_config.num_points
        self.num_zones = np.minimum(processor_config.num_zones, num_points)
        self.distances = np.linspace(
            detector_metadata.start_m,
            detector_metadata.start_m + (num_points - 1) * detector_metadata.step_length_m,
            num_points,
        )
        self.zone_limits = self.create_zones(self.distances, self.num_zones)

        self.inter_enable = detector_config.inter_enable
        self.inter_threshold = detector_config.inter_detection_threshold
        self.inter_zones = np.zeros(self.num_zones, dtype=int)
        self.max_inter_zone = None

        self.intra_enable = detector_config.intra_enable
        self.intra_threshold = detector_config.intra_detection_threshold
        self.intra_zones = np.zeros(self.num_zones, dtype=int)
        self.max_intra_zone = None

    @staticmethod
    def create_zones(distances: npt.NDArray[np.float_], num_zones: int) -> npt.NDArray[np.float_]:
        """Create zones limits based on chosen range and number of zones."""

        if num_zones < distances.size:
            zone_limits = np.linspace(distances[0], distances[-1], num_zones + 1)
            # Only return upper limits
            return zone_limits[1:]  # type: ignore[no-any-return]

        else:
            return distances

    def get_zone_detections(
        self, depthwise_scores: npt.NDArray[np.float_], threshold: float
    ) -> npt.NDArray[np.int_]:
        """Get presence detection result for all zones."""

        zones = np.zeros(self.num_zones, dtype=int)
        zone_detected = False
        limit_idx = 0
        for i, score in enumerate(depthwise_scores):
            if self.distances[i] > self.zone_limits[limit_idx]:
                limit_idx += 1
                zone_detected = False
            if not zone_detected:
                zone_detected = score > threshold
                zones[limit_idx] = 1 if zone_detected else 0

        return zones

    def get_max_presence_zone(self, depthwise_scores: npt.NDArray[np.float_]) -> int:
        """Get the zone with maximum presence score."""

        max_idx = np.argmax(depthwise_scores)
        max_distance = self.distances[max_idx]
        max_zone = 0
        while max_zone < self.num_zones - 1 and max_distance > self.zone_limits[max_zone]:
            max_zone += 1

        return max_zone

    def process(self, result: DetectorResult) -> ProcessorResult:
        max_presence_zone: Optional[int]

        if result.presence_detected:
            # Update zone detections for each detection type.
            if self.inter_enable:
                if result.inter_presence_score > self.inter_threshold:
                    self.inter_zones = self.get_zone_detections(
                        result.inter_depthwise_scores, self.inter_threshold
                    )
                    if not np.any(self.inter_zones):
                        self.inter_zones[self.max_inter_zone] = 1
                    else:
                        self.max_inter_zone = self.get_max_presence_zone(
                            result.inter_depthwise_scores
                        )

                else:
                    self.inter_zones = np.zeros(self.num_zones, dtype=int)
                    self.max_inter_zone = None

            if self.intra_enable:
                if result.intra_presence_score > self.intra_threshold:
                    self.intra_zones = self.get_zone_detections(
                        result.intra_depthwise_scores, self.intra_threshold
                    )
                    if not np.any(self.intra_zones):
                        self.intra_zones[self.max_intra_zone] = 1
                    else:
                        self.max_intra_zone = self.get_max_presence_zone(
                            result.intra_depthwise_scores
                        )

                else:
                    self.intra_zones = np.zeros(self.num_zones, dtype=int)
                    self.max_intra_zone = None

            # max intra zone is prioritized due to faster reaction time.
            if self.max_intra_zone is not None:
                max_presence_zone = self.max_intra_zone
            else:
                max_presence_zone = self.max_inter_zone

            total_zone_detections = np.maximum(self.inter_zones, self.intra_zones)

        else:
            max_presence_zone = None
            self.inter_zones = np.zeros(self.num_zones, dtype=int)
            self.intra_zones = np.zeros(self.num_zones, dtype=int)
            total_zone_detections = np.zeros(self.num_zones, dtype=int)
            self.max_inter_zone = None
            self.max_intra_zone = None

        return ProcessorResult(
            zone_limits=self.zone_limits,
            max_presence_zone=max_presence_zone,
            total_zone_detections=total_zone_detections,
            inter_zone_detections=self.inter_zones,
            max_inter_zone=self.max_inter_zone,
            intra_zone_detections=self.intra_zones,
            max_intra_zone=self.max_intra_zone,
        )
