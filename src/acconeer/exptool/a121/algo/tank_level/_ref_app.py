# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import enum
import warnings
from typing import Any, Dict, Optional, Tuple

import attrs
import h5py
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool import type_migration as tm
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo import (
    AlgoConfigBase,
    Controller,
    PeakSortingMethod,
    ReflectorShape,
)
from acconeer.exptool.a121.algo._utils import ENVELOPE_FWHM_M
from acconeer.exptool.a121.algo.distance import (
    PRF_REMOVED_ET_VERSION,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    ThresholdMethod,
    _DetectorConfig_v0,
)
from acconeer.exptool.a121.algo.distance._detector import detector_context_timeline

from ._processor import (
    Processor,
    ProcessorConfig,
    ProcessorExtraResult,
    ProcessorLevelStatus,
    ProcessorResult,
)


PARTIAL_RANGE_FWHM_FACTOR = 2.0  # Sets the minimal partial range in number of FWHM widths


class RangeMode(enum.Enum):
    """Tank Level range mode."""

    FULL_RANGE = enum.auto()
    PARTIAL_RANGE = enum.auto()


@attributes_doc
@attrs.mutable(kw_only=True)
class RefAppConfig(AlgoConfigBase):
    start_m: float = attrs.field(default=0.03)
    """Start of measurement range."""

    end_m: float = attrs.field(default=0.5)
    """End of measurement range."""

    max_step_length: Optional[int] = attrs.field(default=None)
    """If set, limits the step length.

    If no argument is provided, the step length is automatically calculated based on the profile.

    Reducing the step length increases SNR through more efficient distance filtering, while
    increasing the measurement time and the processing load.
    """

    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    """Specifies the longest allowed profile.

    If no argument is provided, the highest possible profile without interference of direct
    leakage is used to maximize SNR.

    A lower profile improves the radial resolution.
    """

    close_range_leakage_cancellation: bool = attrs.field(default=False)
    """Enable close range leakage cancellation logic.

    Close range leakage cancellation refers to the process of measuring close to the
    sensor(<100mm) by first characterizing the direct leakage, and then subtracting it
    from the measured sweep in order to isolate the signal component of interest.

    The close range leakage cancellation process requires the sensor to be installed in its
    intended geometry with free space in front of the sensor during detector calibration.
    """

    level_tracking_active: bool = attrs.field(default=False)
    """Track level and measure only a smaller partial range to save power"""

    partial_tracking_range_m: float = attrs.field(default=1.0)
    """Minimum partial range window length used during level tracking"""

    signal_quality: float = attrs.field(default=15.0)
    """Signal quality (dB).

    High quality equals higher HWAAS and better SNR but increases power consumption."""

    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    """Threshold method"""

    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )
    """Sorting method of estimated distances.

    The distance estimates are sorted according to the selected strategy, before being return
    by th application.
    """

    reflector_shape: ReflectorShape = attrs.field(
        default=ReflectorShape.GENERIC,
        converter=ReflectorShape,
    )
    """Reflector shape."""

    num_frames_in_recorded_threshold: int = attrs.field(default=100)
    """Number of frames used when calibrating threshold.

    A lower number reduce calibration time and a higher number results in a more statistically
    significant threshold.
    """

    fixed_threshold_value: float = attrs.field(default=100.0)
    """Value of fixed amplitude threshold."""

    fixed_strength_threshold_value: float = attrs.field(default=0.0)
    """Value of fixed strength threshold."""

    threshold_sensitivity: float = attrs.field(default=0.5)
    """Sensitivity of threshold.

    High sensitivity equals low detection threshold, low sensitivity equals high detection
    threshold."""

    update_rate: Optional[float] = attrs.field(default=50.0)
    """Sets the detector update rate."""

    median_filter_length: int = attrs.field(default=5)
    """Length of the median filter used to improve robustness of the result."""

    num_medians_to_average: int = attrs.field(default=1)
    """Number of medians averaged to obtain the final level."""

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

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if self.threshold_method == ThresholdMethod.RECORDED and self.level_tracking_active:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "threshold_method",
                    "Cannot use recorded threshold when level tracking is activated.",
                )
            )
        if self.close_range_leakage_cancellation and self.level_tracking_active:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "close_range_leakage_cancellation",
                    "Cannot use close range leakage cancellation when level tracking is activated.",
                )
            )
        if (
            self.level_tracking_active
            and self.partial_tracking_range_m is not None
            and self.partial_tracking_range_m
            <= ENVELOPE_FWHM_M[self.max_profile] * PARTIAL_RANGE_FWHM_FACTOR
        ):
            validation_results.append(
                a121.ValidationError(
                    self,
                    "partial_tracking_range_m",
                    (
                        "Partial tracking range must be larger than "
                        f"{ENVELOPE_FWHM_M[self.max_profile] * PARTIAL_RANGE_FWHM_FACTOR:.3f} "
                        "for the selected max_profile."
                    ),
                )
            )
        if (
            self.level_tracking_active
            and self.partial_tracking_range_m is not None
            and self.partial_tracking_range_m >= (self.end_m - self.start_m)
        ):
            validation_results.append(
                a121.ValidationError(
                    self,
                    "partial_tracking_range_m",
                    "Partial tracking range must be smaller than (end_m - start_m).",
                )
            )
        if self.end_m < self.start_m:
            validation_results.append(
                a121.ValidationError(
                    self,
                    "start_m",
                    "Must be smaller than 'Range end'",
                )
            )

            validation_results.append(
                a121.ValidationError(
                    self,
                    "end_m",
                    "Must be greater than 'Range start'",
                )
            )

        if self.max_step_length is not None and (
            not utils.is_divisor_of(24, self.max_step_length)
            and not utils.is_multiple_of(24, self.max_step_length)
        ):
            valid_step_length = next(
                sl
                for sl in range(self.max_step_length, 0, -1)
                if utils.is_divisor_of(24, sl) or utils.is_multiple_of(24, sl)
            )
            validation_results.append(
                a121.ValidationWarning(
                    self,
                    "max_step_length",
                    "Actual step length will be rounded down "
                    + f"to the closest valid step length ({valid_step_length}).",
                )
            )

        return validation_results

    def to_detector_config(self) -> DetectorConfig:
        """Nominal full range detector config"""

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
            update_rate=None,
        )

    def to_detector_level_tracking_config(self, level: float) -> DetectorConfig:
        """Level tracking detector config."""
        full_range_config = self.to_detector_config()
        distance = self.end_m - level
        if self.partial_tracking_range_m is not None:
            partial_range_width = max(
                self.partial_tracking_range_m,
                ENVELOPE_FWHM_M[self.max_profile] * PARTIAL_RANGE_FWHM_FACTOR,
            )
        else:
            partial_range_width = ENVELOPE_FWHM_M[self.max_profile] * PARTIAL_RANGE_FWHM_FACTOR
        sub_start = max(distance - partial_range_width / 2, full_range_config.start_m)
        sub_end = min(distance + partial_range_width / 2, full_range_config.end_m)

        return DetectorConfig(
            start_m=sub_start,
            end_m=sub_end,
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
            update_rate=None,
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
        self.range_mode: RangeMode = RangeMode.FULL_RANGE
        self.detector_config = self.config.to_detector_config()

        self._detector = Detector(
            client=self.client,
            sensor_ids=[self.sensor_id],
            detector_config=self.detector_config,
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
        self.context = context

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

        # Detector start() called with recorder and algo group input.
        # Since the detector is swapped and/or stopped during runtime without
        # recorder and algo group input a side effect is that, only the
        # algo group and context for the initial full range config is saved to the record.
        self._detector.start(recorder=recorder, _algo_group=algo_group)

        self.started = True

    def _get_next_mean_median(self) -> Tuple[ProcessorResult, RefAppExtraResult]:
        current_peak_status = None
        # fetch new data until processor has accumulated enough data to give result.
        # get_next() will be called {median_filter_length * num_medians_to_average} times.
        while current_peak_status is None:
            result = self._detector.get_next()
            processor_result = self._processor.process(
                detector_result=result,
                detector_start_m=self._detector.config.start_m,
            )
            current_peak_status = processor_result.peak_status

        ref_app_extra_result = RefAppExtraResult(
            processor_extra_result=processor_result.extra_result, detector_result=result
        )
        return (processor_result, ref_app_extra_result)

    def get_next(self) -> RefAppResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        if not self._detector.started:
            self._detector.calibrate_detector()
            self._detector.start(recorder=None, _algo_group=None)
        (processor_result, ref_app_extra_result) = self._get_next_mean_median()

        if self.config.update_rate is not None:
            self._detector.stop_detector()

        # Level tracking (partial/full range) state machine.
        if self.range_mode == RangeMode.FULL_RANGE:
            # Do nothing while in full range mode. I.e sensor range is kept constant in this
            # mode as full range
            if (
                processor_result.peak_status == ProcessorLevelStatus.IN_RANGE
                and processor_result.filtered_level is not None
                and self.config.level_tracking_active
            ):
                # change to tracking mode. I.e partial range
                detector_config = self.config.to_detector_level_tracking_config(
                    processor_result.filtered_level
                )
                self._swap_detector(detector_config)
                self.range_mode = RangeMode.PARTIAL_RANGE
        elif self.range_mode == RangeMode.PARTIAL_RANGE:
            # update config for level tracking
            if (
                processor_result.peak_status != ProcessorLevelStatus.IN_RANGE
                or processor_result.filtered_level is None
            ):
                # No peak detected (NO_DETECTION) or outside range (OUT_OF_RANGE or OVERFLOW).
                # Go to full range mode
                detector_config = self.config.to_detector_config()
                self._swap_detector(detector_config)
                self.range_mode = RangeMode.FULL_RANGE
            else:
                detector_config = self.config.to_detector_level_tracking_config(
                    processor_result.filtered_level
                )
                self._swap_detector(detector_config)

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

        if self._detector.started:
            recorder_result = self._detector.stop()
        else:
            recorder_result = self._detector.stop_recorder()

        self.started = False

        return recorder_result

    def _swap_detector(self, config: DetectorConfig) -> None:
        """Create new detector object. No recorder is sent to detector.
        The recorder is however attached to the client at initialization of the ref app."""
        if self._detector.started:
            self._detector.stop_detector()
        self._detector = Detector(
            client=self.client,
            sensor_ids=[self.sensor_id],
            detector_config=config,
            context=self.context,
        )


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
class _RefAppConfig_v1(AlgoConfigBase):
    start_m: float = attrs.field(default=0.03)
    end_m: float = attrs.field(default=0.5)
    max_step_length: Optional[int] = attrs.field(default=None)
    max_profile: a121.Profile = attrs.field(default=a121.Profile.PROFILE_5, converter=a121.Profile)
    close_range_leakage_cancellation: bool = attrs.field(default=False)
    signal_quality: float = attrs.field(default=15.0)
    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR,
        converter=ThresholdMethod,
    )
    peaksorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )
    reflector_shape: ReflectorShape = attrs.field(
        default=ReflectorShape.GENERIC,
        converter=ReflectorShape,
    )
    num_frames_in_recorded_threshold: int = attrs.field(default=100)
    fixed_threshold_value: float = attrs.field(default=100.0)
    fixed_strength_threshold_value: float = attrs.field(default=0.0)
    threshold_sensitivity: float = attrs.field(default=0.5)
    update_rate: Optional[float] = attrs.field(default=50.0)
    median_filter_length: int = attrs.field(default=5)
    num_medians_to_average: int = attrs.field(default=1)

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        return []

    def migrate(self) -> RefAppConfig:
        return RefAppConfig(
            start_m=self.start_m,
            end_m=self.end_m,
            max_step_length=self.max_step_length,
            max_profile=self.max_profile,
            close_range_leakage_cancellation=self.close_range_leakage_cancellation,
            signal_quality=self.signal_quality,
            update_rate=self.update_rate,
            median_filter_length=self.median_filter_length,
            num_medians_to_average=self.num_medians_to_average,
            threshold_method=self.threshold_method,
            reflector_shape=self.reflector_shape,
            peaksorting_method=self.peaksorting_method,
            num_frames_in_recorded_threshold=self.num_frames_in_recorded_threshold,
            fixed_threshold_value=self.fixed_threshold_value,  # float
            fixed_strength_threshold_value=self.fixed_strength_threshold_value,  # float
            threshold_sensitivity=self.threshold_sensitivity,  # float
            level_tracking_active=False,
            partial_tracking_range_m=0.0,  # not used
        )


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


def always_raise_an_error_when_migrating_v0(_: _DetectorConfig_v0) -> _RefAppConfig_v1:
    msg = f"Try opening the file in an earlier version of ET <= {PRF_REMOVED_ET_VERSION}"
    raise BadMigrationPathError(msg)


ref_app_config_timeline = (
    tm.start(_RefAppConfig_v0)
    .load(str, _RefAppConfig_v0.from_json, fail=[TypeError])
    .nop()
    .epoch(_RefAppConfig_v1, always_raise_an_error_when_migrating_v0, fail=[BadMigrationPathError])
    .load(str, _RefAppConfig_v1.from_json, fail=[TypeError])
    .nop()
    .epoch(RefAppConfig, _RefAppConfig_v1.migrate, fail=[])
    .load(str, RefAppConfig.from_json, fail=[TypeError])
)
