# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import enum
from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt
from scipy.signal import filtfilt

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_optional_ndarray_isclose
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    AlgoParamEnum,
    AlgoProcessorConfigBase,
    ProcessorBase,
    ReflectorShape,
    _convert_multiple_amplitudes_to_strengths,
    find_peaks,
    get_distance_filter_coeffs,
    get_distance_filter_edge_margin,
    get_distance_offset,
    interpolate_peaks,
)

from . import _thresholds as thresholds
from ._views import RangeSweepConfig


DEFAULT_SC_BG_NUM_STD_DEV = 6.0
DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE = 100.0
DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE = 0.0
DEFAULT_THRESHOLD_SENSITIVITY = 0.5


class MeasurementType(AlgoParamEnum):
    CLOSE_RANGE = enum.auto()
    FAR_RANGE = enum.auto()


class ProcessorMode(AlgoParamEnum):
    DISTANCE_ESTIMATION = enum.auto()
    RECORDED_THRESHOLD_CALIBRATION = enum.auto()


class ThresholdMethod(AlgoParamEnum):
    """Threshold methods.
    ``CFAR`` Constant False Alarm Rate.
    ``FIXED`` Fixed amplitude threshold.
    ``FIXED_STRENGTH`` Fixed strength threshold.
    ``RECORDED`` Recorded threshold."""

    CFAR = enum.auto()
    FIXED = enum.auto()
    FIXED_STRENGTH = enum.auto()
    RECORDED = enum.auto()


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    processor_mode: ProcessorMode = attrs.field(
        default=ProcessorMode.DISTANCE_ESTIMATION, converter=ProcessorMode
    )
    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR, converter=ThresholdMethod
    )
    measurement_type: MeasurementType = attrs.field(
        default=MeasurementType.FAR_RANGE, converter=MeasurementType
    )
    reflector_shape: ReflectorShape = attrs.field(
        default=ReflectorShape.GENERIC, converter=ReflectorShape
    )
    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE)
    fixed_strength_threshold_value: float = attrs.field(
        default=DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE
    )

    def _collect_validation_results(
        self, config: Optional[a121.SessionConfig]
    ) -> list[a121.ValidationResult]:
        return []


@attrs.frozen(kw_only=True)
class ProcessorContext:
    direct_leakage: Optional[npt.NDArray[np.complex128]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    phase_jitter_comp_ref: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_threshold_mean_sweep: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_threshold_noise_std: Optional[list[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    bg_noise_std: Optional[list[float]] = attrs.field(default=None)
    reference_temperature: Optional[int] = attrs.field(default=None)
    loopback_peak_location_m: Optional[float] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    abs_sweep: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    used_threshold: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    distances_m: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )


@attrs.frozen(kw_only=True)
class ProcessorResult:
    estimated_distances: Optional[list[float]] = attrs.field(default=None)
    estimated_strengths: Optional[list[float]] = attrs.field(default=None)
    near_edge_status: Optional[bool] = attrs.field(default=None)
    recorded_threshold_mean_sweep: Optional[npt.NDArray[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    recorded_threshold_noise_std: Optional[list[np.float64]] = attrs.field(
        default=None, eq=attrs_optional_ndarray_isclose
    )
    extra_result: ProcessorExtraResult = attrs.field(factory=ProcessorExtraResult)


class DistanceFilter:
    NARROW_DISTANCE_FILTER_BREAKPOINT = 40  # corresponding to 0.1m

    def __init__(self, profile: a121.Profile, start_point: int, step_length: int) -> None:
        use_narrow_filter = start_point < self.NARROW_DISTANCE_FILTER_BREAKPOINT

        self._margin = get_distance_filter_edge_margin(profile, step_length)
        self._b, self._a = get_distance_filter_coeffs(
            profile, step_length, narrow_filter=use_narrow_filter
        )

    def apply(self, sweep_or_frame: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        """
        Apply the distance filter. Result is cropped to the valid range.

        If a frame (2D array) is passed, the sweeps are averaged before filtering.
        """
        sweep = self._to_sweep(sweep_or_frame)
        filtered: npt.NDArray[np.complex128] = filtfilt(self._b, self._a, sweep)
        end = -self._margin if self._margin > 0 else None
        return filtered[self._margin : end]

    def compute_envelope(
        self, sweep_or_frame: npt.NDArray[np.complex128]
    ) -> npt.NDArray[np.float64]:
        """Return the magnitude of the distance-filtered sweep (cropped to valid range)."""
        filtered_sweep = self.apply(sweep_or_frame)
        return np.abs(filtered_sweep)

    @property
    def margin(self) -> int:
        return self._margin

    def _to_sweep(self, sweep_or_frame: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        if sweep_or_frame.ndim == 1:
            return sweep_or_frame
        if sweep_or_frame.ndim == 2:
            result: npt.NDArray[np.complex128] = sweep_or_frame.mean(axis=0)
            return result

        msg = f"Expected sweep_or_frame to be 1D or 2D, got {sweep_or_frame.ndim}D."
        raise ValueError(msg)


class Processor(ProcessorBase[ProcessorResult]):
    """Distance processor

    For all used subsweeps, the ``profile`` and ``step_length`` must be the same.

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    :param subsweep_indexes:
        The subsweep indexes to be processed. If ``None``, all subsweeps will be used.
    :param context: Context
    """

    # Standard deviation of angle in direct leakage over multiple sensor restarts.
    PHASE_JITTER_RESTART_STD = 0.05

    CLOSE_RANGE_LOOPBACK_IDX = 0
    CLOSE_RANGE_DIST_IDX = 1

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: Optional[list[int]] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        if context is None:
            context = ProcessorContext()

        if subsweep_indexes is None:
            subsweep_indexes = list(range(sensor_config.num_subsweeps))

        if (processor_config.measurement_type is MeasurementType.CLOSE_RANGE) and (
            context.direct_leakage is None or context.phase_jitter_comp_ref is None
        ):
            msg = "Sufficient processor context not provided"
            raise ValueError(msg)

        # range_subsweep_indexes holds the subsweep indexes corresponding to range measurements.
        # - Far range - all subsweeps are range measurements.
        # - Close range - The first subsweep is used for phase jitter compensation and the while
        #   the second is a range measurement. The location of each is indicated by
        #   CLOSE_RANGE_LOOPBACK_IDX and CLOSE_RANGE_DIST_IDX.
        if processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            self._validate_close_config(sensor_config, subsweep_indexes)
            self.range_subsweep_indexes = [self.CLOSE_RANGE_DIST_IDX]
        elif processor_config.measurement_type == MeasurementType.FAR_RANGE:
            self.range_subsweep_indexes = subsweep_indexes
        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.context = context

        self.processor_config.validate(self.sensor_config)
        self.range_sweep_config = RangeSweepConfig.from_sensor_config(
            self.sensor_config, self.range_subsweep_indexes
        )
        self.range_subsweep_configs = self.range_sweep_config.subsweep_configs
        self.profile = self.range_sweep_config.profile
        self.step_length = self.range_sweep_config.step_length
        self.approx_step_length_m = self.step_length * APPROX_BASE_STEP_LENGTH_M
        self.start_point = self.range_sweep_config.start_point
        self.num_points = self.range_sweep_config.num_points
        self.distance_points = self.range_sweep_config.distance_points
        self.start_points = self.range_sweep_config.start_points
        self.hwaas_per_subsweep = self.range_sweep_config.hwaas_per_subsweep
        self.subsweep_slices = self.range_sweep_config.subsweep_slices

        # Matched filter
        self.distance_filter = DistanceFilter(self.profile, self.start_point, self.step_length)
        self.filt_margin = self.distance_filter.margin

        # Valid points after filtering
        self.start_point_cropped = self.start_point + self.filt_margin * self.step_length
        self.num_points_cropped = self.num_points - 2 * self.filt_margin
        self.subsweep_slices_cropped = self.subsweep_slices.cropped(edge_margin=self.filt_margin)

        # Distances in meter
        self.base_step_length_m = self.metadata.base_step_length_m
        self.step_length_m = self.step_length * self.base_step_length_m
        self.distances_m = (
            self.base_step_length_m * self.distance_points[self.filt_margin : -self.filt_margin]
        )

        self.processor_mode = processor_config.processor_mode
        self.threshold_method = processor_config.threshold_method
        self.num_stds_in_threshold = thresholds.sensitivity_to_standard_deviations(
            self.processor_config.threshold_sensitivity
        )

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            self._init_process_distance_estimation()
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            self._init_recorded_threshold_calibration()
        else:
            raise RuntimeError

    @classmethod
    def _validate_close_config(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> None:
        ERROR_MSG = "Incorrect subsweep config for close range measurement"

        if subsweep_indexes != [cls.CLOSE_RANGE_LOOPBACK_IDX, cls.CLOSE_RANGE_DIST_IDX]:
            raise ValueError(ERROR_MSG)

        if (
            not sensor_config.subsweeps[cls.CLOSE_RANGE_LOOPBACK_IDX].enable_loopback
            and sensor_config.subsweeps[cls.CLOSE_RANGE_DIST_IDX].enable_loopback
        ):
            raise ValueError(ERROR_MSG)

    def process(self, result: a121.Result) -> ProcessorResult:
        range_subframes = [result.subframes[i] for i in self.range_subsweep_indexes]
        frame = np.concatenate(range_subframes, axis=1)
        if self.processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            lb_angle = np.angle(result.subframes[self.CLOSE_RANGE_LOOPBACK_IDX]).astype(float)
            if (
                self.processor_config.processor_mode
                == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION
            ):
                lb_angle += self.PHASE_JITTER_RESTART_STD * self.num_stds_in_threshold

            frame = self._apply_phase_jitter_compensation(self.context, frame, lb_angle)

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            return self._process_distance_estimation(frame, result.temperature)
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            return self._process_recorded_threshold_calibration(frame)

        raise RuntimeError

    @staticmethod
    def _apply_phase_jitter_compensation(
        context: ProcessorContext,
        frame: npt.NDArray[np.complex128],
        lb_angle: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.complex128]:
        if context.direct_leakage is None or context.phase_jitter_comp_ref is None:
            msg = "Sufficient context not provided"
            raise ValueError(msg)

        adjusted_leakage = context.direct_leakage * np.exp(
            -1j * (context.phase_jitter_comp_ref - lb_angle)
        )

        return frame - adjusted_leakage  # type: ignore[no-any-return]

    def _init_process_distance_estimation(self) -> None:
        self.threshold: thresholds.Threshold

        if self.threshold_method == ThresholdMethod.RECORDED:
            if (
                self.context.recorded_threshold_mean_sweep is None
                or self.context.recorded_threshold_noise_std is None
                or self.context.bg_noise_std is None
                or self.context.reference_temperature is None
            ):
                msg = "Missing recorded threshold inputs in context"
                raise ValueError(msg)

            self.threshold = thresholds.RecordedThreshold(
                recorded_mean_sweep=self.context.recorded_threshold_mean_sweep,
                rec_noise_std_per_subsweep=self.context.recorded_threshold_noise_std,
                bg_noise_std_per_subsweep=self.context.bg_noise_std,
                reference_temperature=self.context.reference_temperature,
                sensitivity=self.processor_config.threshold_sensitivity,
                profile=self.profile,
                subsweep_slices_cropped=self.subsweep_slices_cropped,
            )

        elif self.threshold_method == ThresholdMethod.FIXED:
            self.threshold = thresholds.FixedThreshold(
                fixed_value=self.processor_config.fixed_threshold_value,
            )

        elif self.threshold_method == ThresholdMethod.FIXED_STRENGTH:
            if self.context.bg_noise_std is None:
                msg = "Missing bg_noise_std in context"
                raise ValueError(msg)

            self.threshold = thresholds.FixedStrengthThreshold(
                fixed_strength=self.processor_config.fixed_strength_threshold_value,
                bg_noise_std_per_subsweep=self.context.bg_noise_std,
                reflector_shape=self.processor_config.reflector_shape,
                profile=self.profile,
                step_length=self.step_length,
                distance_points=self.distance_points[self.filt_margin : -self.filt_margin],
                start_points=self.start_points,
                hwaas_per_subsweep=self.hwaas_per_subsweep,
            )

        elif self.threshold_method == ThresholdMethod.CFAR:
            self.threshold = thresholds.CfarThreshold(
                sensitivity=self.processor_config.threshold_sensitivity,
                bg_noise_std_per_subsweep=self.context.bg_noise_std,
                profile=self.profile,
                start_point=self.start_point,
                step_length=self.step_length,
                subsweep_slices_cropped=self.subsweep_slices_cropped,
            )

        self.offset_m = get_distance_offset(
            self.context.loopback_peak_location_m, self.profile, self.context.reference_temperature
        )

    def _process_distance_estimation(
        self, frame: npt.NDArray[np.complex128], temperature: int
    ) -> ProcessorResult:
        abs_sweep = self.distance_filter.compute_envelope(frame)
        threshold_values = self.threshold.compute(abs_sweep, temperature)
        found_peaks_idx = find_peaks(abs_sweep, threshold_values)
        estimated_distances, estimated_amplitudes = interpolate_peaks(
            abs_sweep,
            found_peaks_idx,
            self.start_point_cropped,
            self.step_length,
            self.base_step_length_m,
        )

        # Crop to valid range after thresholding
        m = self.threshold.margin
        valid_range = slice(m, -m or None)
        abs_sweep = abs_sweep[valid_range]
        threshold_values = threshold_values[valid_range]
        distances_m = self.distances_m[valid_range]
        extra_result = ProcessorExtraResult(
            abs_sweep=abs_sweep,
            used_threshold=threshold_values,
            distances_m=distances_m,
        )

        # Calculate strengths before applying offset as the offset could push the estimated
        # distance into the next subsweep, resulting in strengths being calculated with wrong
        # sensor parameters.
        estimated_strengths = _convert_multiple_amplitudes_to_strengths(
            estimated_amplitudes,
            estimated_distances,
            self.range_subsweep_configs,
            self.context.bg_noise_std,  # type: ignore[arg-type]
            self.processor_config.reflector_shape,
        )

        estimated_distances = [dist - self.offset_m for dist in estimated_distances]

        near_edge_status = self._detect_close_object(abs_sweep, threshold_values)

        return ProcessorResult(
            estimated_distances=estimated_distances,
            estimated_strengths=estimated_strengths,
            near_edge_status=near_edge_status,
            extra_result=extra_result,
        )

    def _init_recorded_threshold_calibration(self) -> None:
        self.bg_sc_mean = np.zeros(self.num_points_cropped)
        self.bg_sc_sum_squared_bg_sweeps = np.zeros(self.num_points_cropped)
        self.sc_bg_num_sweeps = 1.0

    def _process_recorded_threshold_calibration(
        self, frame: npt.NDArray[np.complex128]
    ) -> ProcessorResult:
        min_num_sweeps_in_valid_threshold = 2

        abs_sweep = self.distance_filter.compute_envelope(frame)
        self.bg_sc_mean += abs_sweep
        self.bg_sc_sum_squared_bg_sweeps += np.square(abs_sweep)
        mean_sweep = self.bg_sc_mean / self.sc_bg_num_sweeps
        mean_square = self.bg_sc_sum_squared_bg_sweeps / self.sc_bg_num_sweeps
        square_mean = np.square(mean_sweep)

        if min_num_sweeps_in_valid_threshold <= self.sc_bg_num_sweeps:
            sc_bg_sweep_std = np.sqrt(
                np.abs(mean_square - square_mean)
                * self.sc_bg_num_sweeps
                / (self.sc_bg_num_sweeps - 1)
            )

            assert self.context.bg_noise_std is not None
            recorded_threshold_noise_std = []
            for subsweep_slice, tx_off_noise_std in zip(
                self.subsweep_slices_cropped, self.context.bg_noise_std
            ):
                # Clamp negative values to zero as the variable is in square root below.
                sigma_square_diff = np.clip(
                    sc_bg_sweep_std[subsweep_slice] ** 2 - tx_off_noise_std**2,
                    a_min=0,
                    a_max=None,
                )
                recorded_threshold_noise_std.append(
                    np.mean(np.sqrt(sigma_square_diff) / mean_sweep[subsweep_slice])
                )
        else:
            recorded_threshold_noise_std = None

        self.sc_bg_num_sweeps += 1

        extra_result = ProcessorExtraResult(abs_sweep=abs_sweep)
        return ProcessorResult(
            extra_result=extra_result,
            recorded_threshold_mean_sweep=mean_sweep,
            recorded_threshold_noise_std=recorded_threshold_noise_std,
        )

    @staticmethod
    def _detect_close_object(
        abs_sweep: npt.NDArray[np.float64], threshold_values: npt.NDArray[np.float64]
    ) -> bool:
        """This function determine if an object is present close to the start point, but
        not far enough into the measurement interval to result in a distinct peak.

        The detection is done by analyzing the shape of the envelope close to the edge of the
        measurement interval.
        """

        # Check that the segment is of sufficient length to perform analysis.
        if abs_sweep.shape[0] < 6:
            return False

        return bool(
            np.sum(abs_sweep[0:3]) >= np.sum(abs_sweep[3:6])
            and abs_sweep[0] >= threshold_values[0]
        )


def calculate_bg_noise_std(
    subframe: npt.NDArray[np.complex128], subsweep_config: a121.SubsweepConfig
) -> float:
    profile = subsweep_config.profile
    start_point = subsweep_config.start_point
    step_length = subsweep_config.step_length
    distance_filter = DistanceFilter(profile, start_point, step_length)
    abs_sweep = distance_filter.compute_envelope(subframe)

    return float(np.sqrt(np.mean(np.square(abs_sweep))))
