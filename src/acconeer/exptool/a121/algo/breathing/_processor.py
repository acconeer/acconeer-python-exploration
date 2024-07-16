# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import enum
from typing import List, Optional

import attrs
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc
from scipy.signal import butter

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_isclose
from acconeer.exptool.a121.algo import (
    ENVELOPE_FWHM_M,
    AlgoParamEnum,
    AlgoProcessorConfigBase,
    ProcessorBase,
    exponential_smoothing_coefficient,
)
from acconeer.exptool.a121.algo.presence import Processor as PresenceProcessor
from acconeer.exptool.a121.algo.presence import ProcessorConfig as PresenceProcessorConfig
from acconeer.exptool.a121.algo.presence import ProcessorResult as PresenceProcessorResult


class AppState(AlgoParamEnum):
    """Breathing app state."""

    INIT_STATE = enum.auto()

    NO_PRESENCE_DETECTED = enum.auto()
    """No presence detected."""

    INTRA_PRESENCE_DETECTED = enum.auto()
    """Intra presence detected."""

    DETERMINE_DISTANCE_ESTIMATE = enum.auto()
    """Determining distance using presence."""

    ESTIMATE_BREATHING_RATE = enum.auto()
    """Estimating breathing rate."""


@attributes_doc
@attrs.mutable(kw_only=True)
class BreathingProcessorConfig(AlgoProcessorConfigBase):
    lowest_breathing_rate: float = attrs.field(default=6.0)
    """Lowest anticipated breathing rate (breaths per minute)."""

    highest_breathing_rate: float = attrs.field(default=60.0)
    """Highest anticipated breathing rate (breaths per minute)."""

    time_series_length_s: float = attrs.field(default=20.0)
    """Time series length (s)."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> List[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.sensor_config.frame_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "frame_rate",
                    "Must be set",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class BreathingProcessorExtraResult:
    psd: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    frequencies: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    breathing_motion: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    time_vector: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    breathing_rate_history: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)
    all_breathing_rate_history: npt.NDArray[np.float64] = attrs.field(eq=attrs_ndarray_isclose)


@attrs.mutable(kw_only=True)
class BreathingProcessorResult:
    breathing_rate: Optional[float] = attrs.field(default=None)
    """Estimated breathing rate. Breaths per minute."""

    extra_result: BreathingProcessorExtraResult
    """Extra result, only used for visualization."""


class BreathingProcessor(ProcessorBase[BreathingProcessorResult]):
    """Breathing rate processor."""

    SECONDS_IN_MINUTE: float = 60.0
    HISTORY_S = SECONDS_IN_MINUTE * 2.0

    # Type declarations
    start_point: int
    end_point: int
    sparse_iq_buffer: npt.NDArray[np.complex128]
    filt_sparse_iq_buffer: npt.NDArray[np.complex128]
    angle_buffer: npt.NDArray[np.float64]
    filt_angle_buffer: npt.NDArray[np.float64]
    breathing_motion_buffer: npt.NDArray[np.float64]
    breathing_rate_history: npt.NDArray[np.float64]
    all_breathing_rate_history: npt.NDArray[np.float64]

    start_time: float
    init_counter: int
    point_counter: int
    prev_angle: Optional[float]
    lp_filt_ampl: Optional[float]
    angle_unwrapped: npt.NDArray[np.float64]

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        processor_config: BreathingProcessorConfig,
    ):
        assert sensor_config.frame_rate is not None

        lowest_breathing_rate_hz = processor_config.lowest_breathing_rate / self.SECONDS_IN_MINUTE
        highest_breathing_rate_hz = (
            processor_config.highest_breathing_rate / self.SECONDS_IN_MINUTE
        )
        self.frame_rate = sensor_config.frame_rate
        self.time_series_length_s = processor_config.time_series_length_s
        self.time_series_length = int(self.time_series_length_s * self.frame_rate)
        self.padded_time_series_length = 2 ** (int(np.log2(self.time_series_length)) + 1)
        self.analysis_overlap = int(self.time_series_length / 2)
        self.num_points = sensor_config.num_points

        # Filter coefficients.
        self.b_static, self.a_static = butter(
            N=2, Wn=lowest_breathing_rate_hz, btype="lowpass", fs=self.frame_rate
        )
        self.b_angle, self.a_angle = butter(
            N=2,
            Wn=[lowest_breathing_rate_hz, highest_breathing_rate_hz],
            btype="bandpass",
            fs=self.frame_rate,
        )
        self.sf = exponential_smoothing_coefficient(self.frame_rate, self.time_series_length_s)

        # PSD frequency vector.
        self.frequencies = np.fft.rfftfreq(self.padded_time_series_length, 1 / self.frame_rate)
        self.time_vector = np.linspace(-self.HISTORY_S, 0, int(self.frame_rate * self.HISTORY_S))

        self.reinitialize_processor(0, self.num_points)

    def process(self, result: a121.Result) -> BreathingProcessorResult:
        frame = result.frame[:, self.start_point : self.end_point]
        mean_sweep = frame.mean(axis=0)

        # Estimate static component
        self.sparse_iq_buffer = np.roll(self.sparse_iq_buffer, shift=1, axis=0)
        self.sparse_iq_buffer[0] = mean_sweep

        filt_sparse_iq = -np.sum(
            self.a_static[1:][:, np.newaxis] * self.filt_sparse_iq_buffer, axis=0
        ) + np.sum(self.b_static[:, np.newaxis] * self.sparse_iq_buffer, axis=0)

        self.filt_sparse_iq_buffer = np.roll(self.filt_sparse_iq_buffer, shift=1, axis=0)
        self.filt_sparse_iq_buffer[0] = filt_sparse_iq

        # Remove static components by subtracting the estimated mean.
        zm_sweep = mean_sweep - filt_sparse_iq
        angle = np.angle(zm_sweep)

        if self.prev_angle is None or self.lp_filt_ampl is None:
            self.prev_angle = angle
            self.lp_filt_ampl = np.abs(zm_sweep)

        # Filter the amplitude(used when weighting psds from the measured distances).
        assert self.lp_filt_ampl is not None
        self.lp_filt_ampl = self.sf * self.lp_filt_ampl + (1 - self.sf) * np.abs(zm_sweep)

        # Unwrap the angles.
        angle_diff = angle - self.prev_angle
        angle_diff[np.pi < angle_diff] -= 2 * np.pi
        angle_diff[angle_diff < -np.pi] += 2 * np.pi
        self.angle_unwrapped = self.angle_unwrapped + angle_diff
        self.angle_buffer = np.roll(self.angle_buffer, shift=1, axis=0)
        self.angle_buffer[0] = self.angle_unwrapped
        self.prev_angle = angle

        # Bandpass filter angles.
        filt_angle = -np.sum(
            self.a_angle[1:][:, np.newaxis] * self.filt_angle_buffer, axis=0
        ) + np.sum(self.b_angle[:, np.newaxis] * self.angle_buffer, axis=0)
        self.filt_angle_buffer = np.roll(self.filt_angle_buffer, shift=1, axis=0)
        self.filt_angle_buffer[0] = filt_angle

        # Add filtered angle to breathing motion fifo buffer.
        self.breathing_motion_buffer = np.roll(self.breathing_motion_buffer, shift=-1, axis=0)
        self.breathing_motion_buffer[-1] = filt_angle

        # Calculate psd of signal.
        windowed_breathing_motion_buffer = (
            self.breathing_motion_buffer * np.hamming(self.time_series_length)[:, np.newaxis]
        )
        psd = np.fft.rfft(
            windowed_breathing_motion_buffer, axis=0, n=self.padded_time_series_length
        )
        # Omit **2 to reduce processing as it does not alter the result.
        psd = np.abs(psd)
        assert self.lp_filt_ampl is not None
        psd_weighted = np.sum(psd * self.lp_filt_ampl, axis=1) / np.sum(self.lp_filt_ampl)

        # Interpolate around peak to gain better resolution.
        # Wait until data of a full time series is available.
        peak_loc = np.argmax(psd_weighted)
        if peak_loc != 0 and self.time_series_length < self.init_counter:
            estimated_frequency = self._peak_interpolation(
                psd_weighted[peak_loc - 1 : peak_loc + 2],
                self.frequencies[peak_loc - 1 : peak_loc + 2],
            )
            estimated_breathing_rate = estimated_frequency * self.SECONDS_IN_MINUTE
        else:
            self.init_counter += 1
            estimated_breathing_rate = None

        # Shift breathing rate history and add latest estimate.
        self.all_breathing_rate_history = np.roll(self.all_breathing_rate_history, shift=-1)
        self.all_breathing_rate_history[-1] = estimated_breathing_rate
        self.breathing_rate_history = np.roll(self.breathing_rate_history, shift=-1)

        # Report breathing rate if enough time has elapsed since last estimate.
        if self.time_series_length - self.analysis_overlap <= self.point_counter:
            self.breathing_rate_history[-1] = estimated_breathing_rate
            self.point_counter = 0
        else:
            self.breathing_rate_history[-1] = np.nan
            self.point_counter += 1

        # Prepare extra result, used for plotting.
        extra_result = BreathingProcessorExtraResult(
            psd=psd_weighted,
            frequencies=self.frequencies,
            breathing_motion=self.breathing_motion_buffer[:, self.center_distance_idx],
            time_vector=self.time_vector,
            all_breathing_rate_history=self.all_breathing_rate_history,
            breathing_rate_history=self.breathing_rate_history,
        )

        return BreathingProcessorResult(
            breathing_rate=estimated_breathing_rate, extra_result=extra_result
        )

    def reinitialize_processor(self, start_point: int, end_point: int) -> None:
        self.start_point = start_point
        self.end_point = end_point

        num_points_to_analyze = self.end_point - self.start_point
        self.center_distance_idx = int(num_points_to_analyze / 2)

        # Memory of IIR filters.
        self.sparse_iq_buffer = np.zeros(
            shape=(self.b_static.size, num_points_to_analyze), dtype="complex128"
        )
        self.filt_sparse_iq_buffer = np.zeros(
            shape=(self.a_static.size - 1, num_points_to_analyze), dtype="complex128"
        )

        self.angle_buffer = np.zeros(shape=(self.b_angle.size, num_points_to_analyze))
        self.filt_angle_buffer = np.zeros(shape=(self.a_angle.size - 1, num_points_to_analyze))

        # Memory for breathing motion time series.
        self.breathing_motion_buffer = np.zeros(
            shape=(self.time_series_length, num_points_to_analyze)
        )

        # State variables.
        self.init_counter = 0
        self.prev_angle = None
        self.lp_filt_ampl = None
        self.point_counter = 0
        self.angle_unwrapped = np.zeros(shape=num_points_to_analyze)

        # Memory for breathing rate history.
        self.breathing_rate_history = np.full(
            shape=int(self.frame_rate * self.HISTORY_S), fill_value=np.nan
        )
        self.all_breathing_rate_history = np.full(
            shape=int(self.frame_rate * self.HISTORY_S), fill_value=np.nan
        )

    @staticmethod
    def _peak_interpolation(y: npt.NDArray[np.float64], x: npt.NDArray[np.float64]) -> float:
        """Quadratic interpolation of three points.

        Derivation:
        https://math.stackexchange.com/questions/680646/get-polynomial-function-from-3-points
        """
        a = (x[0] * (y[2] - y[1]) + x[1] * (y[0] - y[2]) + x[2] * (y[1] - y[0])) / (
            (x[0] - x[1]) * (x[0] - x[2]) * (x[1] - x[2])
        )
        b = (y[1] - y[0]) / (x[1] - x[0]) - a * (x[0] + x[1])
        peak_loc = -b / (2 * a)
        return float(peak_loc)


def get_presence_config() -> PresenceProcessorConfig:
    presence_config = PresenceProcessorConfig()
    presence_config.intra_detection_threshold = 4.0
    return presence_config


class ProcessorConfig(AlgoProcessorConfigBase):
    num_distances_to_analyze: int = attrs.field(default=3)
    """Indicates the number of distance to analyzed, centered around the distance where presence
    is detected."""

    distance_determination_duration: float = attrs.field(default=5.0)
    """Time for the presence processor to determine distance to presence."""

    use_presence_processor: bool = attrs.field(default=True)
    """If True, use the presence processor to determine distance to subject."""

    breathing_config: BreathingProcessorConfig = attrs.field(factory=BreathingProcessorConfig)

    presence_config: PresenceProcessorConfig = attrs.field(factory=get_presence_config)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> List[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.sensor_config.frame_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "frame_rate",
                    "Must be set",
                )
            )

        return validation_results


@attrs.mutable(kw_only=True)
class ProcessorResult:
    app_state: AppState
    """Application state."""

    distances_being_analyzed: Optional[tuple[int, int]] = None
    """Range where breathing is being analyzed."""

    presence_result: PresenceProcessorResult
    """Presence processor result."""

    breathing_result: Optional[BreathingProcessorResult] = attrs.field(default=None)
    """Breathing processor result."""


class Processor(ProcessorBase[ProcessorResult]):
    """Breathing rate super-processor.

    Handles execution of the presence processor and the breathing processor.
    """

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        processor_config: ProcessorConfig,
        metadata: a121.Metadata,
    ):
        assert sensor_config.frame_rate is not None

        self.sensor_config = sensor_config
        self.metadata = metadata

        self.presence_processor = PresenceProcessor(
            sensor_config=sensor_config,
            metadata=self.metadata,
            processor_config=processor_config.presence_config,
        )

        self.breathing_processor = BreathingProcessor(
            sensor_config=sensor_config,
            processor_config=processor_config.breathing_config,
        )

        self.breathing_processor.reinitialize_processor(0, sensor_config.num_points)

        # Parameters
        self.intra_detection_threshold = processor_config.presence_config.intra_detection_threshold
        self.use_presence_processor = processor_config.use_presence_processor
        self.presence_threshold = ENVELOPE_FWHM_M[sensor_config.profile] * 2.0
        self.num_distances_to_analyze_half_width = int(
            processor_config.num_distances_to_analyze / 2.0
        )
        self.distance_determination_duration = (
            processor_config.distance_determination_duration * sensor_config.frame_rate
        )
        self.sf = exponential_smoothing_coefficient(
            sensor_config.frame_rate, processor_config.distance_determination_duration / 4.0
        )
        self.num_points = sensor_config.num_points

        # State variables
        self.presence_distance_has_init = False
        self.distance_determination_counter = 0
        self.app_state: AppState = AppState.INIT_STATE
        self.prev_app_state = AppState.INIT_STATE
        self.base_presence_distance: Optional[float] = None

    def process(self, result: a121.Result) -> ProcessorResult:
        presence_result = self.presence_processor.process(result=result)

        self._determine_app_state(presence_result)

        self._update_presence_distance(presence_result.presence_distance)

        processor_result = ProcessorResult(
            app_state=self.app_state, presence_result=presence_result
        )

        self._perform_action_based_on_app_state(result, processor_result)

        self.prev_app_state = self.app_state

        return processor_result

    def _determine_app_state(self, presence_result: PresenceProcessorResult) -> None:
        if not presence_result.presence_detected:
            self.app_state = AppState.NO_PRESENCE_DETECTED

        elif self.intra_detection_threshold < presence_result.intra_presence_score:
            self.app_state = AppState.INTRA_PRESENCE_DETECTED

        elif self.base_presence_distance is None and self.use_presence_processor:
            self.app_state = AppState.DETERMINE_DISTANCE_ESTIMATE

        elif (
            not self.use_presence_processor
            or self.distance_determination_duration <= self.distance_determination_counter
        ):
            self.app_state = AppState.ESTIMATE_BREATHING_RATE

        else:
            # Do not change app state
            pass

    def _update_presence_distance(self, presence_distance: float) -> None:
        # Calculate and filter presence distance.
        if not self.presence_distance_has_init:
            self.presence_distance = presence_distance
            self.presence_distance_has_init = True

        assert self.presence_distance is not None
        self.presence_distance = self.presence_distance * self.sf + presence_distance * (
            1 - self.sf
        )

        # Determine if presence location has changed.
        if self.base_presence_distance is not None and self.presence_threshold < np.abs(
            self.base_presence_distance - self.presence_distance
        ):
            self.base_presence_distance = None

    def _perform_action_based_on_app_state(
        self, result: a121.Result, processor_result: ProcessorResult
    ) -> None:
        # Perform action based on app state
        if (
            self.app_state == AppState.INTRA_PRESENCE_DETECTED
            or self.app_state == AppState.NO_PRESENCE_DETECTED
        ):
            self.base_presence_distance = None

        elif self.app_state == AppState.DETERMINE_DISTANCE_ESTIMATE:
            if self.app_state != self.prev_app_state:
                self.distance_determination_counter = 0
            else:
                self.distance_determination_counter += 1
                self.base_presence_distance = self.presence_distance

        elif self.app_state == AppState.ESTIMATE_BREATHING_RATE:
            if self.app_state != self.prev_app_state:
                if self.use_presence_processor:
                    center_idx = self._base_presence_distance_to_point()
                    start_point = max(0, center_idx - self.num_distances_to_analyze_half_width)
                    end_point = min(
                        center_idx + self.num_distances_to_analyze_half_width + 1,
                        self.num_points,
                    )
                else:
                    start_point = 0
                    end_point = self.num_points

                self.breathing_processor.reinitialize_processor(
                    start_point=start_point,
                    end_point=end_point,
                )

            processor_result.distances_being_analyzed = (
                self.breathing_processor.start_point,
                self.breathing_processor.end_point,
            )
            processor_result.breathing_result = self.breathing_processor.process(result)

        else:
            msg = "Invalid app state"
            raise NotImplementedError(msg)

    def _base_presence_distance_to_point(self) -> int:
        """Calculates the closest point of a distance in meters"""
        assert self.base_presence_distance is not None
        assert not isinstance(self.metadata, list)

        measured_points = (
            self.sensor_config.start_point
            + np.arange(self.sensor_config.num_points) * self.sensor_config.step_length
        )
        center_point = int(self.base_presence_distance / self.metadata.base_step_length_m)
        return int(np.argmin(np.abs(measured_points - center_point)))
