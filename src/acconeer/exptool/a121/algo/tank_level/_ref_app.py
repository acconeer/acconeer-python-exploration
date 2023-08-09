# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional, Tuple

import attrs
import h5py

from acconeer.exptool import a121
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import Controller
from acconeer.exptool.a121.algo.distance import (
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
)

from ._processor import Processor, ProcessorConfig, ProcessorExtraResult, ProcessorLevelStatus


@attrs.mutable(kw_only=True)
class RefAppConfig(DetectorConfig):
    start_m: float = attrs.field(default=0.03)
    """Start of measurement range."""
    end_m: float = attrs.field(default=0.5)
    """End of measurement range."""
    median_filter_length: int = attrs.field(default=5)
    """Length of the median filter used to improve robustness of the result."""
    num_medians_to_average: int = attrs.field(default=1)
    """Number of medians averaged to obtain the final level."""

    @start_m.validator
    def _(self, _: Any, value: float) -> None:
        if value < Detector.MIN_DIST_M:
            raise ValueError(f"Cannot start measurements closer than {Detector.MIN_DIST_M}m")

    @end_m.validator
    def _(self, _: Any, value: float) -> None:
        if value > Detector.MAX_DIST_M:
            raise ValueError(f"Cannot measure further than {Detector.MAX_DIST_M}m")

    def to_detector_config(self) -> DetectorConfig:
        return DetectorConfig(
            start_m=self.start_m - 0.015,
            end_m=self.end_m * 1.05,
            max_step_length=self.max_step_length,
            max_profile=self.max_profile,
            signal_quality=self.signal_quality,
            threshold_method=self.threshold_method,
            peaksorting_method=self.peaksorting_method,
            reflector_shape=self.reflector_shape,
            num_frames_in_recorded_threshold=self.num_frames_in_recorded_threshold,
            fixed_threshold_value=self.fixed_threshold_value,
            threshold_sensitivity=self.threshold_sensitivity,
            update_rate=self.update_rate,
        )


@attrs.frozen(kw_only=True)
class RefAppExtraResult:
    processor_extra_result: ProcessorExtraResult
    detector_result: Dict[int, DetectorResult]


RefAppContext = DetectorContext


@attrs.frozen(kw_only=True)
class RefAppResult:
    peak_detected: Optional[bool]
    """True if a peak (level) is detected, False if no peak is
    detected, or None if a result is not available."""
    peak_status: Optional[ProcessorLevelStatus]
    """Status assigned to the detected peak."""
    level: Optional[float]
    """Liquid level relative to the base of the tank."""
    extra_result: RefAppExtraResult
    """Extra result: Only used for the plots in the GUI."""


class RefApp(Controller[RefAppConfig, RefAppResult]):
    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        config: RefAppConfig,
        context: Optional[RefAppContext] = None,
    ) -> None:
        super().__init__(client=client, config=config)
        self.sensor_id = sensor_id

        detector_config = self.config.to_detector_config()

        self._detector = Detector(
            client=self.client,
            sensor_ids=[self.sensor_id],
            detector_config=detector_config,
            context=context,
        )

        processor_config = ProcessorConfig(
            median_filter_length=self.config.median_filter_length,
            num_medians_to_average=self.config.num_medians_to_average,
            tank_range_start_m=self.config.start_m,
            tank_range_end_m=self.config.end_m,
        )

        self._processor = Processor(processor_config)

        self.started = False

    def calibrate(self) -> None:
        self._detector.calibrate_detector()

    def start(
        self, recorder: Optional[a121.Recorder] = None, algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            raise RuntimeError("Already started")

        if recorder is not None:
            if isinstance(recorder, a121.H5Recorder):
                algo_group = recorder.require_algo_group("tank_level")
                _record_algo_data(algo_group, self.sensor_id, self.config, self._detector.context)
            else:
                # Should never happen as we currently only have the H5Recorder
                warnings.warn("Will not save algo data")

        self._detector.start(recorder=recorder, _algo_group=algo_group)

        self.started = True

    def get_next(self) -> RefAppResult:
        if not self.started:
            raise RuntimeError("Not started")

        result = self._detector.get_next()

        processor_result = self._processor.process(result)

        ref_app_extra_result = RefAppExtraResult(
            processor_extra_result=processor_result.extra_result, detector_result=result
        )

        return RefAppResult(
            peak_detected=processor_result.peak_detected,
            peak_status=processor_result.peak_status,
            level=processor_result.filtered_level,
            extra_result=ref_app_extra_result,
        )

    def update_config(self, config: RefAppConfig) -> None:
        raise NotImplementedError

    def stop(self) -> Any:
        if not self.started:
            raise RuntimeError("Already stopped")

        recorder_result = self._detector.stop()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group, sensor_id: int, config: RefAppConfig, context: RefAppContext
) -> None:
    algo_group.create_dataset("sensor_id", data=sensor_id, track_times=False)

    _create_h5_string_dataset(algo_group, "config", config.to_json())

    context_group = algo_group.create_group("tank_level_context")
    context.to_h5(context_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, RefAppConfig, RefAppContext]:
    sensor_id = int(algo_group["sensor_id"][()])
    config = RefAppConfig.from_json(algo_group["config"][()])

    context_group = algo_group["tank_level_context"]
    tank_level_context = DetectorContext.from_h5(context_group)

    return sensor_id, config, tank_level_context
