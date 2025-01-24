# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import warnings
from typing import Any, Dict, Optional, Tuple

import attrs
import h5py
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool import type_migration as tm
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import Controller
from acconeer.exptool.a121.algo.distance import (
    PRF_REMOVED_ET_VERSION,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    _DetectorConfig_v0,
)
from acconeer.exptool.a121.algo.distance._detector import detector_context_timeline

from ._processor import Processor, ProcessorConfig, ProcessorExtraResult, ProcessorLevelStatus


@attributes_doc
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
    close_range_leakage_cancellation: bool = attrs.field(default=False)
    """Enable close range leakage cancellation logic.

    Close range leakage cancellation refers to the process of measuring close to the
    sensor(<100mm) by first characterizing the direct leakage, and then subtracting it
    from the measured sweep in order to isolate the signal component of interest.

    The close range leakage cancellation process requires the sensor to be installed in its
    intended geometry with free space in front of the sensor during detector calibration.
    """

    @start_m.validator
    def _(self, _: Any, value: float) -> None:
        if value < Detector.MIN_DIST_M:
            msg = f"Cannot start measurements closer than {Detector.MIN_DIST_M}m"
            raise ValueError(msg)

    @end_m.validator
    def _(self, _: Any, value: float) -> None:
        if value > Detector.MAX_DIST_M:
            msg = f"Cannot measure further than {Detector.MAX_DIST_M}m"
            raise ValueError(msg)

    def to_detector_config(self) -> DetectorConfig:
        return DetectorConfig(
            start_m=self.start_m - 0.015,
            end_m=min(self.end_m * 1.05, 23.0),
            max_step_length=self.max_step_length,
            max_profile=self.max_profile,
            close_range_leakage_cancellation=self.close_range_leakage_cancellation,
            signal_quality=self.signal_quality,
            threshold_method=self.threshold_method,
            peaksorting_method=self.peaksorting_method,
            reflector_shape=self.reflector_shape,
            num_frames_in_recorded_threshold=self.num_frames_in_recorded_threshold,
            fixed_strength_threshold_value=self.fixed_strength_threshold_value,
            fixed_threshold_value=self.fixed_threshold_value,
            threshold_sensitivity=self.threshold_sensitivity,
            update_rate=self.update_rate,
        )


@attrs.frozen(kw_only=True)
class RefAppExtraResult:
    processor_extra_result: ProcessorExtraResult
    detector_result: Dict[int, DetectorResult]


RefAppContext = DetectorContext
ref_app_context_timeline = detector_context_timeline


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
            msg = "Already started"
            raise RuntimeError(msg)

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
            msg = "Not started"
            raise RuntimeError(msg)

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
            msg = "Already stopped"
            raise RuntimeError(msg)

        recorder_result = self._detector.stop()

        self.started = False

        return recorder_result


def _record_algo_data(
    algo_group: h5py.Group, sensor_id: int, config: RefAppConfig, context: RefAppContext
) -> None:
    algo_group.create_dataset("sensor_id", data=sensor_id, track_times=False)

    _create_h5_string_dataset(algo_group, "config", config.to_json())

    context_group = algo_group.create_group("tank_level_context")
    opser.serialize(context, context_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, RefAppConfig, RefAppContext]:
    sensor_id = int(algo_group["sensor_id"][()])

    try:
        config = ref_app_config_timeline.migrate(algo_group["config"][()].decode())
    except tm.core.MigrationErrorGroup as exc:
        msg = ""
        match = exc.subgroup(BadMigrationPathError)
        if match is not None:
            # Add more details from exception thrown
            for exc_arg in match.exceptions[0].args:
                if isinstance(exc_arg, str):
                    print(exc_arg)
                    msg += f", {exc_arg}"

        raise TypeError(msg) from exc

    context_group = algo_group["tank_level_context"]
    tank_level_context = ref_app_context_timeline.migrate(context_group)

    return sensor_id, config, tank_level_context


@attrs.mutable
@attrs.mutable(kw_only=True)
class _RefAppConfig_v0(_DetectorConfig_v0):
    start_m: float = attrs.field(default=0.03)
    end_m: float = attrs.field(default=0.5)
    median_filter_length: int = attrs.field(default=5)
    num_medians_to_average: int = attrs.field(default=1)
    close_range_leakage_cancellation: bool = attrs.field(default=False)

    def to_detector_config(self) -> RefAppConfig:
        return RefAppConfig(
            start_m=self.start_m - 0.015,
            end_m=min(self.end_m * 1.05, 23.0),
            max_step_length=self.max_step_length,
            max_profile=self.max_profile,
            close_range_leakage_cancellation=self.close_range_leakage_cancellation,
            signal_quality=self.signal_quality,
            threshold_method=self.threshold_method,
            peaksorting_method=self.peaksorting_method,
            reflector_shape=self.reflector_shape,
            num_frames_in_recorded_threshold=self.num_frames_in_recorded_threshold,
            fixed_strength_threshold_value=self.fixed_strength_threshold_value,
            fixed_threshold_value=self.fixed_threshold_value,
            threshold_sensitivity=self.threshold_sensitivity,
            update_rate=self.update_rate,
        )

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []


class BadMigrationPathError(Exception): ...


def always_raise_an_error_when_migrating_v0(_: _RefAppConfig_v0) -> RefAppConfig:
    msg = f"Try opening the file in an earlier version of ET <= {PRF_REMOVED_ET_VERSION}"
    raise BadMigrationPathError(msg)


ref_app_config_timeline = (
    tm.start(_RefAppConfig_v0)
    .load(str, _RefAppConfig_v0.from_json, fail=[TypeError])
    .nop()
    .epoch(RefAppConfig, always_raise_an_error_when_migrating_v0, fail=[BadMigrationPathError])
    .load(str, RefAppConfig.from_json, fail=[TypeError])
)
