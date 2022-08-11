# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import copy
import enum
from typing import Any, List, Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt
from scipy.signal import butter, filtfilt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoConfigBase, AlgoParamEnum, ProcessorBase


DEFAULT_SC_BG_NUM_STD_DEV = 6.0
DEFAULT_FIXED_THRESHOLD_VALUE = 100.0
DEFAULT_THRESHOLD_SENSITIVITY = 0.25
DEFAULT_CFAR_ONE_SIDED = False


class MeasurementType(AlgoParamEnum):
    CLOSE_RANGE = enum.auto()
    FAR_RANGE = enum.auto()


class ProcessorMode(AlgoParamEnum):
    DISTANCE_ESTIMATION = enum.auto()
    LEAKAGE_CALIBRATION = enum.auto()
    RECORDED_THRESHOLD_CALIBRATION = enum.auto()


class ThresholdMethod(AlgoParamEnum):
    """Threshold methods.
    ``CFAR`` Constant False Alarm Rate.
    ``FIXED`` Fixed threshold.
    ``RECORDED`` Recorded threshold."""

    CFAR = enum.auto()
    FIXED = enum.auto()
    RECORDED = enum.auto()


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoConfigBase):
    processor_mode: ProcessorMode = attrs.field(
        default=ProcessorMode.DISTANCE_ESTIMATION, converter=ProcessorMode
    )
    threshold_method: ThresholdMethod = attrs.field(
        default=ThresholdMethod.CFAR, converter=ThresholdMethod
    )
    measurement_type: MeasurementType = attrs.field(
        default=MeasurementType.FAR_RANGE, converter=MeasurementType
    )
    threshold_sensitivity: float = attrs.field(default=DEFAULT_THRESHOLD_SENSITIVITY)
    fixed_threshold_value: float = attrs.field(default=DEFAULT_FIXED_THRESHOLD_VALUE)
    cfar_guard_length_m: Optional[float] = attrs.field(default=None)
    cfar_window_length_m: Optional[float] = attrs.field(default=None)
    cfar_one_sided: bool = attrs.field(default=DEFAULT_CFAR_ONE_SIDED)


@attrs.frozen(kw_only=True)
class ProcessorContext:
    direct_leakage: Optional[npt.NDArray[np.complex_]] = attrs.field(default=None)
    phase_jitter_comp_ref: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    recorded_threshold_mean_sweep: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    recorded_threshold_noise_std: Optional[List[np.float_]] = attrs.field(default=None)
    bg_noise_std: Optional[List[float]] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    abs_sweep: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    used_threshold: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    distances_m: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class ProcessorResult:
    estimated_distances: Optional[list[float]] = attrs.field(default=None)
    estimated_amplitudes: Optional[list[float]] = attrs.field(default=None)
    recorded_threshold_mean_sweep: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    recorded_threshold_noise_std: Optional[list[np.float_]] = attrs.field(default=None)
    direct_leakage: Optional[npt.NDArray[np.complex_]] = attrs.field(default=None)
    phase_jitter_comp_reference: Optional[npt.NDArray[np.float_]] = attrs.field(default=None)
    extra_result: ProcessorExtraResult = attrs.field(factory=ProcessorExtraResult)


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    """Distance processor

    For all used subsweeps, the ``profile`` and ``step_length`` must be the same.

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    :param subsweep_indexes:
        The subsweep indexes to be processed. If ``None``, all subsweeps will be used.
    :param context: Context
    """

    ENVELOPE_FWHM_M = {
        a121.Profile.PROFILE_1: 0.04,
        a121.Profile.PROFILE_2: 0.07,
        a121.Profile.PROFILE_3: 0.14,
        a121.Profile.PROFILE_4: 0.19,
        a121.Profile.PROFILE_5: 0.32,
    }

    APPROX_BASE_STEP_LENGTH_M = 2.5e-3

    CFAR_GUARD_LENGTH_ADJUSTMENT = 4
    CFAR_WINDOW_LENGTH_ADJUSTMENT = 0.25

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

        if (
            processor_config.measurement_type is MeasurementType.CLOSE_RANGE
            and processor_config.processor_mode is not ProcessorMode.LEAKAGE_CALIBRATION
        ):
            if context.direct_leakage is None or context.phase_jitter_comp_ref is None:
                raise ValueError("Sufficient processor context not provided")

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
        range_subsweep_configs = self._get_subsweep_configs(
            sensor_config, self.range_subsweep_indexes
        )
        self._validate_range_configs(range_subsweep_configs)

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.context = context

        self.profile = self._get_profile(range_subsweep_configs)
        self.step_length = self._get_step_length(range_subsweep_configs)
        self.approx_step_length_m = self.step_length * self.APPROX_BASE_STEP_LENGTH_M
        self.start_point = self._get_start_point(range_subsweep_configs)
        self.num_points = self._get_num_points(range_subsweep_configs)

        self.base_step_length_m = self.metadata.base_step_length_m
        self.step_length_m = self.step_length * self.base_step_length_m

        self.filt_margin = self.distance_filter_edge_margin(self.profile, self.step_length)
        self.start_point_cropped = self.start_point + self.filt_margin * self.step_length
        self.num_points_cropped = self.num_points - 2 * self.filt_margin

        self.subsweep_bpts = self._get_subsweep_breakpoints(
            range_subsweep_configs, self.filt_margin
        )

        self.distances_m = (
            self.start_point_cropped + np.arange(self.num_points_cropped) * self.step_length
        ) * self.metadata.base_step_length_m

        (self.b, self.a) = self.get_distance_filter_coeffs(self.profile, self.step_length)

        self.processor_mode = processor_config.processor_mode
        self.threshold_method = processor_config.threshold_method
        self.threshold_sensitivity = self.processor_config.threshold_sensitivity

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            self._init_process_distance_estimation()
        elif self.processor_mode == ProcessorMode.LEAKAGE_CALIBRATION:
            pass
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            self._init_recorded_threshold_calibration()
        else:
            raise RuntimeError

    @classmethod
    def _get_subsweep_configs(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: list[int]
    ) -> list[a121.SubsweepConfig]:
        return [sensor_config.subsweeps[i] for i in subsweep_indexes]

    @classmethod
    def _get_profile(cls, subsweep_configs: list[a121.SubsweepConfig]) -> a121.Profile:
        profiles = {c.profile for c in subsweep_configs}

        if len(profiles) > 1:
            raise ValueError

        (profile,) = profiles
        return profile

    @classmethod
    def _get_step_length(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        step_lengths = {c.step_length for c in subsweep_configs}
        if len(step_lengths) > 1:
            raise ValueError
        (step_length,) = step_lengths
        return step_length

    @classmethod
    def _get_start_point(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        return subsweep_configs[0].start_point

    @classmethod
    def _get_num_points(cls, subsweep_configs: list[a121.SubsweepConfig]) -> int:
        return sum(c.num_points for c in subsweep_configs)

    @classmethod
    def _get_subsweep_breakpoints(
        cls, subsweep_configs: list[a121.SubsweepConfig], filt_margin: int
    ) -> list[int]:
        """Calculate the subsweep breakpoints of the full sweep(including filter margins).

        The breakpoints are calculated as the cumulative sum of the number of points in each
        subsweep. Then, the breakpoints are formed by adding filt_margin to the front
        of the list and subtracted from the last element in the list.
        """

        num_points_in_subsweeps = [
            subsweep_config.num_points for subsweep_config in subsweep_configs
        ]
        bpts = [
            sum(num_points_in_subsweeps[: idx + 1]) for idx in range(len(num_points_in_subsweeps))
        ]
        bpts.insert(0, filt_margin)
        bpts[-1] -= filt_margin
        return bpts

    @classmethod
    def _validate_range_configs(cls, subsweep_configs: list[a121.SubsweepConfig]) -> None:
        cls._validate_range(subsweep_configs)

        for c in subsweep_configs:
            if not c.phase_enhancement:
                raise ValueError

    @classmethod
    def _validate_range(cls, subsweep_configs: list[a121.SubsweepConfig]) -> None:
        step_length = cls._get_step_length(subsweep_configs)

        next_expected_start_point = None

        for c in subsweep_configs:
            if next_expected_start_point is not None:
                if c.start_point != next_expected_start_point:
                    raise ValueError

            next_expected_start_point = c.start_point + c.num_points * step_length

    @classmethod
    def _validate_close_config(
        cls, sensor_config: a121.SensorConfig, subsweep_indexes: List[int]
    ) -> None:
        ERROR_MSG = "Incorrect subsweep config for close range measurement"

        if subsweep_indexes != [cls.CLOSE_RANGE_LOOPBACK_IDX, cls.CLOSE_RANGE_DIST_IDX]:
            raise ValueError(ERROR_MSG)

        subsweep_configs = cls._get_subsweep_configs(sensor_config, subsweep_indexes)

        if (
            not subsweep_configs[cls.CLOSE_RANGE_LOOPBACK_IDX].enable_loopback
            and subsweep_configs[cls.CLOSE_RANGE_DIST_IDX].enable_loopback
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
                lb_angle += self.PHASE_JITTER_RESTART_STD / (self.threshold_sensitivity + 1e-10)

            if self.processor_mode != ProcessorMode.LEAKAGE_CALIBRATION:
                frame = self._apply_phase_jitter_compensation(self.context, frame, lb_angle)

        sweep = frame.mean(axis=0)
        filtered_sweep = filtfilt(self.b, self.a, sweep)
        abs_sweep = np.abs(filtered_sweep)
        abs_sweep = abs_sweep[self.filt_margin : -self.filt_margin]

        if self.processor_mode == ProcessorMode.DISTANCE_ESTIMATION:
            return self._process_distance_estimation(abs_sweep)
        elif self.processor_mode == ProcessorMode.LEAKAGE_CALIBRATION:
            return ProcessorResult(
                phase_jitter_comp_reference=lb_angle,
                direct_leakage=frame,
            )
        elif self.processor_mode == ProcessorMode.RECORDED_THRESHOLD_CALIBRATION:
            return self._process_recorded_threshold_calibration(abs_sweep)

        raise RuntimeError

    @staticmethod
    def _apply_phase_jitter_compensation(
        context: ProcessorContext,
        frame: npt.NDArray[np.complex_],
        lb_angle: npt.NDArray[np.float_],
    ) -> npt.NDArray[np.complex_]:
        if context.direct_leakage is None or context.phase_jitter_comp_ref is None:
            raise ValueError("Sufficient context not provided")

        adjusted_leakage = context.direct_leakage * np.exp(
            -1j * (context.phase_jitter_comp_ref - lb_angle)
        )

        return frame - adjusted_leakage  # type: ignore[no-any-return]

    def _init_process_distance_estimation(self) -> None:
        if self.threshold_method == ThresholdMethod.RECORDED:
            if (
                self.context.recorded_threshold_mean_sweep is None
                or self.context.recorded_threshold_noise_std is None
            ):
                raise ValueError("Missing recorded threshold inputs in context")
        elif self.threshold_method == ThresholdMethod.FIXED:
            self.threshold = np.full(
                self.num_points_cropped, self.processor_config.fixed_threshold_value
            )
        elif self.threshold_method == ThresholdMethod.CFAR:
            self.cfar_abs_noise = np.zeros(shape=self.num_points_cropped)
            if self.context.bg_noise_std is not None:
                for idx, tx_off_noise_std in enumerate(self.context.bg_noise_std):
                    self.cfar_abs_noise[
                        self.subsweep_bpts[idx] : self.subsweep_bpts[idx + 1]
                    ] = tx_off_noise_std
            self.cfar_margin = self.calc_cfar_margin(self.profile, self.step_length)
            self.cfar_one_sided = self.processor_config.cfar_one_sided
            window_length = self._calc_cfar_window_length(self.profile, self.step_length)
            guard_half_length = self._calc_cfar_guard_half_length(self.profile, self.step_length)
            self.idx_cfar_pts = guard_half_length + np.arange(window_length)

    @classmethod
    def _calc_cfar_window_length(cls, profile: a121.Profile, step_length: int) -> int:
        window_length_m = cls.ENVELOPE_FWHM_M[profile] * cls.CFAR_WINDOW_LENGTH_ADJUSTMENT
        step_length_m = step_length * cls.APPROX_BASE_STEP_LENGTH_M
        return max([1, int(window_length_m / step_length_m)])

    @classmethod
    def _calc_cfar_guard_half_length(cls, profile: a121.Profile, step_length: int) -> int:
        guard_length_m = cls.ENVELOPE_FWHM_M[profile] * cls.CFAR_GUARD_LENGTH_ADJUSTMENT
        step_length_m = step_length * cls.APPROX_BASE_STEP_LENGTH_M
        guard_half_length_m = guard_length_m / 2
        return int(guard_half_length_m / step_length_m)

    @classmethod
    def calc_cfar_margin(cls, profile: a121.Profile, step_length: int) -> int:
        return cls._calc_cfar_window_length(
            profile, step_length
        ) + cls._calc_cfar_guard_half_length(profile, step_length)

    def _process_distance_estimation(self, abs_sweep: npt.NDArray[np.float_]) -> ProcessorResult:
        self.threshold = self._update_threshold(abs_sweep)

        found_peaks_idx = self._find_peaks(abs_sweep, self.threshold)
        (estimated_distances, estimated_amplitudes) = self.interpolate_peaks(
            abs_sweep,
            found_peaks_idx,
            self.start_point_cropped,
            self.step_length,
            self.base_step_length_m,
        )

        if self.processor_config.threshold_method == ThresholdMethod.CFAR:
            cfar_margin_slice = slice(self.cfar_margin, -self.cfar_margin)
            extra_result = ProcessorExtraResult(
                abs_sweep=abs_sweep[cfar_margin_slice],
                used_threshold=self.threshold[cfar_margin_slice],
                distances_m=self.distances_m[cfar_margin_slice],
            )
        else:
            extra_result = ProcessorExtraResult(
                abs_sweep=abs_sweep, used_threshold=self.threshold, distances_m=self.distances_m
            )
        return ProcessorResult(
            estimated_distances=estimated_distances,
            estimated_amplitudes=estimated_amplitudes,
            extra_result=extra_result,
        )

    def _init_recorded_threshold_calibration(self) -> None:
        self.bg_sc_mean = np.zeros(self.num_points_cropped)
        self.bg_sc_sum_squared_bg_sweeps = np.zeros(self.num_points_cropped)
        self.sc_bg_num_sweeps = 1.0

    def _process_recorded_threshold_calibration(
        self, abs_sweep: npt.NDArray[np.float_]
    ) -> ProcessorResult:
        min_num_sweeps_in_valid_threshold = 2

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
            for idx, tx_off_noise_std in enumerate(self.context.bg_noise_std):
                # Subtract filt_margin from breakpoint to transform from full to cropped sweep
                subsweep_slice = slice(
                    self.subsweep_bpts[idx] - self.filt_margin,
                    self.subsweep_bpts[idx + 1] - self.filt_margin,
                    1,
                )
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

    def update_config(self, config: ProcessorConfig) -> None:
        ...

    @classmethod
    def get_distance_filter_coeffs(cls, profile: a121.Profile, step_length: int) -> Any:
        wnc = cls.APPROX_BASE_STEP_LENGTH_M * step_length / cls.ENVELOPE_FWHM_M[profile]
        return butter(N=2, Wn=wnc)

    def _update_threshold(self, abs_sweep: npt.NDArray[np.float_]) -> npt.NDArray[np.float_]:
        if self.threshold_method == ThresholdMethod.CFAR:
            return self._calculate_cfar_threshold(
                abs_sweep,
                self.idx_cfar_pts,
                self.threshold_sensitivity,
                self.cfar_one_sided,
                self.cfar_abs_noise,
            )
        elif self.threshold_method == ThresholdMethod.FIXED:
            return self.threshold
        elif self.threshold_method == ThresholdMethod.RECORDED:
            return self._update_recorded_threshold(
                self.context, self.subsweep_bpts, self.threshold_sensitivity, self.filt_margin
            )
        else:
            raise RuntimeError

    @staticmethod
    def _update_recorded_threshold(
        context: ProcessorContext, bpts: list[int], alpha: float, filt_margin: int
    ) -> npt.NDArray[np.float_]:
        assert context.recorded_threshold_mean_sweep is not None
        assert context.recorded_threshold_noise_std is not None
        assert context.bg_noise_std is not None
        threshold = copy.deepcopy(context.recorded_threshold_mean_sweep)

        for idx, (std_tx_off, std_recorded_threshold) in enumerate(
            zip(context.bg_noise_std, context.recorded_threshold_noise_std)
        ):
            # Subtract filt_margin from breakpoint to transform from full to cropped sweep
            subsweep_slice = slice(bpts[idx] - filt_margin, bpts[idx + 1] - filt_margin)
            threshold[subsweep_slice] += np.sqrt(
                (std_tx_off**2 + threshold[subsweep_slice] ** 2 * std_recorded_threshold**2)
                / (alpha + 1e-10)
            )
        return threshold

    @staticmethod
    def _calculate_cfar_threshold(
        abs_sweep: npt.NDArray[np.float_],
        idx_cfar_pts: npt.NDArray[np.int_],
        alpha: float,
        one_side: bool,
        abs_noise_std: npt.NDArray,
    ) -> npt.NDArray[np.float_]:
        threshold = np.full(abs_sweep.shape, np.nan)
        start_idx = int(np.max(idx_cfar_pts))
        if one_side:
            take_relative_indexes = -idx_cfar_pts
            end_idx = abs_sweep.size
        else:
            take_relative_indexes = np.concatenate((-idx_cfar_pts, +idx_cfar_pts), axis=0)
            end_idx = abs_sweep.size - start_idx

        for idx in np.arange(start_idx, end_idx):
            take_indexes = idx + take_relative_indexes
            threshold[idx] = np.mean(np.take(abs_sweep, take_indexes))

        threshold += abs_noise_std
        threshold *= 1.0 / (alpha + 1e-10)
        return threshold

    @staticmethod
    def _find_peaks(
        abs_sweep: npt.NDArray[np.float_], threshold: npt.NDArray[np.float_]
    ) -> list[int]:
        if threshold is None:
            raise ValueError
        found_peaks = []
        d = 1
        N = len(abs_sweep)
        while d < (N - 1):
            if np.isnan(threshold[d - 1]):
                d += 1
                continue
            if np.isnan(threshold[d + 1]):
                break
            if abs_sweep[d] <= threshold[d]:
                d += 2
                continue
            if abs_sweep[d - 1] <= threshold[d - 1]:
                d += 1
                continue
            if abs_sweep[d - 1] >= abs_sweep[d]:
                d += 1
                continue
            d_upper = d + 1
            while True:
                if (d_upper) >= (N - 1):
                    break
                if np.isnan(threshold[d_upper]):
                    break
                if abs_sweep[d_upper] <= threshold[d_upper]:
                    break
                if abs_sweep[d_upper] > abs_sweep[d]:
                    break
                elif abs_sweep[d_upper] < abs_sweep[d]:
                    found_peaks.append(int(np.argmax(abs_sweep[d:d_upper]) + d))
                    break
                else:
                    d_upper += 1
            d = d_upper
        return found_peaks

    @staticmethod
    def interpolate_peaks(
        abs_sweep: npt.NDArray[np.float_],
        peak_idxs: list[int],
        start_point: int,
        step_length: int,
        step_length_m: float,
    ) -> Tuple[list[float], list[float]]:
        estimated_distances = []
        estimated_amplitudes = []
        for peak_idx in peak_idxs:
            # (https://math.stackexchange.com/questions/680646/get-polynomial-function-from-3-points)
            x = np.arange(peak_idx - 1, peak_idx + 2, 1)
            y = abs_sweep[peak_idx - 1 : peak_idx + 2]
            a = (x[0] * (y[2] - y[1]) + x[1] * (y[0] - y[2]) + x[2] * (y[1] - y[0])) / (
                (x[0] - x[1]) * (x[0] - x[2]) * (x[1] - x[2])
            )
            b = (y[1] - y[0]) / (x[1] - x[0]) - a * (x[0] + x[1])
            c = y[0] - a * x[0] ** 2 - b * x[0]
            peak_loc = -b / (2 * a)
            estimated_distances.append((start_point + peak_loc * step_length) * step_length_m)
            estimated_amplitudes.append(a * peak_loc**2 + b * peak_loc + c)
        return estimated_distances, estimated_amplitudes

    @classmethod
    def distance_filter_edge_margin(cls, profile: a121.Profile, step_length: int) -> int:
        return int(
            np.ceil(cls.ENVELOPE_FWHM_M[profile] / (cls.APPROX_BASE_STEP_LENGTH_M * step_length))
        )


def calculate_bg_noise_std(
    subframe: npt.NDArray[np.complex_], subsweep_config: a121.SubsweepConfig
) -> float:
    profile = subsweep_config.profile
    step_length = subsweep_config.step_length
    (B, A) = Processor.get_distance_filter_coeffs(profile, step_length)
    filt_margin = Processor.distance_filter_edge_margin(profile, step_length)

    sweep = subframe.squeeze(axis=0)
    filtered_sweep = filtfilt(B, A, sweep)
    abs_sweep = np.abs(filtered_sweep)
    abs_sweep = abs_sweep[filt_margin:-filt_margin]

    return float(np.std(np.abs(abs_sweep)))


def calculate_offset(result: a121.Result, config: a121.SensorConfig) -> float:

    # Intercept and offset term of offset compensation.
    OFFSET_COMPENSATION_COEFFS = {
        a121.Profile.PROFILE_1: (0.7144381, 0.01057812),
        a121.Profile.PROFILE_2: (0.49220892, 0.00193627),
        a121.Profile.PROFILE_3: (0.55348759, 0.00252287),
        a121.Profile.PROFILE_4: (6.10352993e-01, 2.30125790e-04),
        a121.Profile.PROFILE_5: (0.66277198, -0.00539498),
    }

    (B, A) = Processor.get_distance_filter_coeffs(config.profile, config.step_length)
    sweep = np.squeeze(result.frame, axis=0)
    abs_sweep = np.abs(filtfilt(B, A, sweep))
    peak_idx = [int(np.argmax(abs_sweep))]

    (estimated_dist, _) = Processor.interpolate_peaks(
        abs_sweep=abs_sweep,
        peak_idxs=peak_idx,
        start_point=config.start_point,
        step_length=config.step_length,
        step_length_m=Processor.APPROX_BASE_STEP_LENGTH_M,
    )

    p = OFFSET_COMPENSATION_COEFFS[config.profile]
    return p[0] * estimated_dist[0] + p[1]
