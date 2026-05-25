# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import enum
from abc import abstractmethod
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
    GenericProcessorBase,
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


DEFAULT_FIXED_AMPLITUDE_THRESHOLD_VALUE = 100.0
DEFAULT_FIXED_STRENGTH_THRESHOLD_VALUE = 0.0
DEFAULT_THRESHOLD_SENSITIVITY = 0.5


class MeasurementType(AlgoParamEnum):
    CLOSE_RANGE = enum.auto()
    FAR_RANGE = enum.auto()


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
    estimated_distances: list[float] = attrs.field()
    estimated_strengths: list[float] = attrs.field()
    near_edge_status: bool = attrs.field()
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


class DistanceProcessorBase(GenericProcessorBase[a121.Result, ProcessorResult]):
    """Distance processor base class. Contains logic common for both close-range and far-range processing.

    For all used subsweeps, the ``profile`` and ``step_length`` must be the same.

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    :param subsweep_indexes:
        The subsweep indexes to be processed. If ``None``, all subsweeps will be used.
    :param context: Context
    """

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_indexes: list[int],
        context: ProcessorContext,
    ) -> None:
        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.range_subsweep_indexes = subsweep_indexes
        self.context = context

        self.processor_config.validate(self.sensor_config)

        # Range sweep parameters
        self.range_sweep_config = RangeSweepConfig.from_sensor_config(
            self.sensor_config, self.range_subsweep_indexes
        )
        self.subsweep_configs = self.range_sweep_config.subsweep_configs
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

        # Distance offset calculation
        self.offset_m = get_distance_offset(
            self.context.loopback_peak_location_m, self.profile, self.context.reference_temperature
        )

        # Threshold initialization
        self.threshold: thresholds.Threshold
        self.threshold_method = processor_config.threshold_method
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
        else:
            msg = f"Invalid threshold method {self.threshold_method}. Valid options: {[tm for tm in ThresholdMethod]}."
            raise ValueError(msg)

    def process(self, result: a121.Result) -> ProcessorResult:
        frame = self._prepare_frame_for_distance_estimation(result)
        sweep = frame.mean(axis=0)
        abs_sweep = self.distance_filter.compute_envelope(sweep)
        threshold_values = self.threshold.compute(abs_sweep, result.temperature)
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
            self.subsweep_configs,
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

    @abstractmethod
    def _prepare_frame_for_distance_estimation(
        self, result: a121.Result
    ) -> npt.NDArray[np.complex128]:
        raise NotImplementedError

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


class FarRangeProcessor(DistanceProcessorBase):
    """Distance processor for far-range measurements."""

    def _prepare_frame_for_distance_estimation(
        self, result: a121.Result
    ) -> npt.NDArray[np.complex128]:
        range_subframes = [result.subframes[i] for i in self.range_subsweep_indexes]
        return np.concatenate(range_subframes, axis=1)


class CloseRangeProcessor(DistanceProcessorBase):
    """Distance processor for close-range measurements."""

    CLOSE_RANGE_GROUP_INDEX = 0  # Close-range measurement is always performed in group 0
    LOOPBACK_SUBSWEEP_INDEX = 0  # Used for phase jitter compensation
    DISTANCE_SUBSWEEP_INDEX = 1  # Range measurement, used for distance estimation

    # Standard deviation of angle in direct leakage over multiple sensor restarts.
    PHASE_JITTER_RESTART_STD = 0.05

    @staticmethod
    def apply_phase_jitter_compensation(
        frame: npt.NDArray[np.complex128],
        lb_angle: npt.NDArray[np.float64],
        direct_leakage: npt.NDArray[np.complex128],
        phase_jitter_comp_ref: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.complex128]:
        """Apply phase jitter compensation (requires results of close-range calibration)."""
        adjusted_leakage: npt.NDArray[np.complex128] = direct_leakage * np.exp(
            -1j * (phase_jitter_comp_ref - lb_angle)
        )
        return frame - adjusted_leakage

    @classmethod
    def validate_sensor_config(cls, sensor_config: a121.SensorConfig) -> None:
        if (
            not sensor_config.subsweeps[cls.LOOPBACK_SUBSWEEP_INDEX].enable_loopback
            or sensor_config.subsweeps[cls.DISTANCE_SUBSWEEP_INDEX].enable_loopback
        ):
            msg = (
                "Invalid configuration for close-range measurement. Loopback must be enabled "
                "for loopback subsweep and disabled for range subsweep."
            )
            raise ValueError(msg)

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        context: ProcessorContext,
    ) -> None:
        self.validate_sensor_config(sensor_config)

        if context.direct_leakage is None or context.phase_jitter_comp_ref is None:
            msg = "Sufficient processor context not provided"
            raise ValueError(msg)

        super().__init__(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            subsweep_indexes=[self.DISTANCE_SUBSWEEP_INDEX],
            context=context,
        )

    def _prepare_frame_for_distance_estimation(
        self, result: a121.Result
    ) -> npt.NDArray[np.complex128]:
        lb_angle = np.angle(result.subframes[self.LOOPBACK_SUBSWEEP_INDEX]).astype(float)
        frame = result.subframes[self.DISTANCE_SUBSWEEP_INDEX]
        return self._apply_phase_jitter_compensation(frame, lb_angle)

    def _apply_phase_jitter_compensation(
        self,
        frame: npt.NDArray[np.complex128],
        lb_angle: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.complex128]:
        assert self.context.direct_leakage is not None
        assert self.context.phase_jitter_comp_ref is not None
        return self.apply_phase_jitter_compensation(
            frame, lb_angle, self.context.direct_leakage, self.context.phase_jitter_comp_ref
        )


def Processor(
    *,
    sensor_config: a121.SensorConfig,
    metadata: a121.Metadata,
    processor_config: ProcessorConfig,
    subsweep_indexes: list[int] | None = None,
    context: ProcessorContext | None = None,
) -> DistanceProcessorBase:
    """Factory for distance processors.

    For all used subsweeps, the ``profile`` and ``step_length`` must be the same.

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    :param subsweep_indexes:
        The subsweep indexes to be processed. If ``None``, all subsweeps will be used.
        For close-range measurements, this parameter is ignored and a fixed scheme is used.
    :param context: Context
    """
    if context is None:
        context = ProcessorContext()

    # Determine whether to instantiate CloseRangeProcessor or FarRangeProcessor
    if processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
        return CloseRangeProcessor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            context=context,
        )

    elif processor_config.measurement_type == MeasurementType.FAR_RANGE:
        if subsweep_indexes is None:
            # Use all subsweeps
            subsweep_indexes = list(range(sensor_config.num_subsweeps))

        return FarRangeProcessor(
            sensor_config=sensor_config,
            metadata=metadata,
            processor_config=processor_config,
            subsweep_indexes=subsweep_indexes,
            context=context,
        )

    else:
        msg = (
            f"Invalid measurement type {processor_config.measurement_type}."
            f"Valid options: {[mt.name for mt in MeasurementType]}."
        )
        raise ValueError(msg)


def calculate_bg_noise_std(
    subframe: npt.NDArray[np.complex128], subsweep_config: a121.SubsweepConfig
) -> float:
    profile = subsweep_config.profile
    start_point = subsweep_config.start_point
    step_length = subsweep_config.step_length
    distance_filter = DistanceFilter(profile, start_point, step_length)
    abs_sweep = distance_filter.compute_envelope(subframe)

    return float(np.sqrt(np.mean(np.square(abs_sweep))))
