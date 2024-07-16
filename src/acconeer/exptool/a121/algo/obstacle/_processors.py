# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import copy
from typing import List, Optional

import attrs
import numpy as np
import numpy.typing as npt
from scipy.signal import filtfilt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    PERCEIVED_WAVELENGTH,
    AlgoProcessorConfigBase,
    PeakSortingMethod,
    ProcessorBase,
    _convert_amplitude_to_strength,
    get_distance_filter_coeffs,
    get_distance_filter_edge_margin,
    get_distance_offset,
    get_temperature_adjustment_factors,
)


TEMPERATURE_FILTER_CONSTANT = 0.95

# The same object can be seen at multiple subsweeps, objects close can be mereged.
MERGE_DISTANCE_M = 0.05
MERGE_SPEED_MPS = 0.05


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    num_std_treshold: float = attrs.field(default=5)
    num_mean_treshold: float = attrs.field(default=2)
    peak_sorting_method: PeakSortingMethod = attrs.field(
        default=PeakSortingMethod.STRONGEST,
        converter=PeakSortingMethod,
    )
    max_robot_speed: float = attrs.field(default=0.5)
    dead_reckoning_duration_s: float = attrs.field(default=0.5)
    sensitivity: float = attrs.field(default=0.5)

    def _collect_validation_results(
        self, config: Optional[a121.SessionConfig]
    ) -> list[a121.ValidationResult]:
        return []


@attrs.frozen(kw_only=True)
class Target:
    distance: float = attrs.field(default=None)
    velocity: float = attrs.field(default=None)
    strength: float = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class SubsweepProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    fft_map: npt.NDArray[np.float64] = attrs.field(default=None)
    fft_map_threshold: npt.NDArray[np.float64] = attrs.field(default=None)
    r: npt.NDArray[np.float64] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class SubsweepProcessorResult:
    targets: list[Target] = attrs.field(factory=list)
    extra_result: SubsweepProcessorExtraResult = attrs.field(factory=None)


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    dv: float = attrs.field(default=None)  # velocity difference between fft-bins


@attrs.frozen(kw_only=True)
class ProcessorResult:
    targets: list[Target] = attrs.field(factory=list)
    time: float = attrs.field(default=None)
    extra_result: ProcessorExtraResult = attrs.field(factory=ProcessorExtraResult)
    subsweeps_extra_results: List[SubsweepProcessorExtraResult] = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class SubsweepProcessorContext:
    sub_sweep_idx: int = attrs.field(default=None)


@attrs.frozen(kw_only=True)
class ProcessorContext:
    update_rate: float = attrs.field()
    mean_sweeps: list[npt.NDArray[np.float64]] = attrs.field(factory=list)
    std_sweeps: list[npt.NDArray[np.float64]] = attrs.field(factory=list)
    reference_temperature: Optional[float] = attrs.field(default=None)
    loopback_peak_location_m: float = attrs.field(default=0.0)


class SubsweepProcessor:
    """Obstacle processor

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    """

    LOOPBACK_START_IDX = -48

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        processor_config: ProcessorConfig,
        proc_context: ProcessorContext,
        ssproc_context: Optional[SubsweepProcessorContext] = None,
    ) -> None:
        self.proc_context = proc_context
        if ssproc_context is None:
            self.ssproc_context = SubsweepProcessorContext()
        else:
            self.ssproc_context = ssproc_context

        self.sensor_config = sensor_config
        self.processor_config = processor_config

        # Threshold setting
        self.num_std_threshold = processor_config.num_std_treshold
        self.num_mean_threshold = processor_config.num_mean_treshold

        # Calbration result
        self.true_zero_dist_idx = 0

        self.offset_m = get_distance_offset(
            self.proc_context.loopback_peak_location_m,
            sensor_config.profile,
            self.proc_context.reference_temperature,
        )

        if self.sensor_config.sweep_rate is None:
            self.sensor_config.sweep_rate = 100

        self.num_points = sensor_config.num_points
        self.dv = (
            PERCEIVED_WAVELENGTH
            / self.sensor_config.sweeps_per_frame
            * self.sensor_config.sweep_rate
        )
        (self.b, self.a) = get_distance_filter_coeffs(
            sensor_config.profile, sensor_config.step_length
        )
        self.fwhm_points = ENVELOPE_FWHM_M[sensor_config.profile] / (
            APPROX_BASE_STEP_LENGTH_M * sensor_config.step_length
        )

        self.filt_margin = get_distance_filter_edge_margin(
            sensor_config.profile,
            sensor_config.step_length,
        )

        # Extra
        self.r = APPROX_BASE_STEP_LENGTH_M * (
            sensor_config.start_point
            + self.filt_margin * sensor_config.step_length
            + sensor_config.step_length * np.arange(self.num_points - 2 * self.filt_margin)
        )

    def process(
        self, subframe: npt.NDArray[np.complex128], temperature: float
    ) -> SubsweepProcessorResult:
        assert self.proc_context.reference_temperature is not None

        # Depth filtering of each sweep
        filtered_subframe = self.apply_depth_filter(subframe)

        # Range downsampling and fft in the sweep dimension
        fftframe = np.fft.fft(filtered_subframe, axis=0)
        abs_fftframe = np.abs(fftframe)
        abs_fftframe_extra = np.copy(abs_fftframe)  # Copy for plotting

        sig_factor, noise_factor = get_temperature_adjustment_factors(
            reference_temperature=self.proc_context.reference_temperature,
            current_temperature=temperature,
            profile=self.sensor_config.profile,
        )

        sig_factor = (
            1 / sig_factor
        )  # After get_temperature_adjustment_factors updated, this inverted.

        fft_map_threshold = np.tile(
            noise_factor
            * self.num_std_threshold
            * self.proc_context.std_sweeps[self.ssproc_context.sub_sweep_idx]
            * np.sqrt(self.sensor_config.sweeps_per_frame),
            (self.sensor_config.sweeps_per_frame, 1),
        )
        fft_map_threshold[0, :] = (
            fft_map_threshold[0, :]
            + sig_factor
            * self.num_mean_threshold
            * np.abs(self.proc_context.mean_sweeps[self.ssproc_context.sub_sweep_idx])
            * self.sensor_config.sweeps_per_frame
        )

        targets = []

        bg_noise_stds = self.proc_context.std_sweeps[self.ssproc_context.sub_sweep_idx]

        diff = abs_fftframe - fft_map_threshold
        spf = self.sensor_config.sweeps_per_frame
        while np.any(diff > 0):
            idx_max = np.unravel_index(np.argmax(diff), diff.shape)
            i_dist = get_interpolated_range_peak_index(
                diff[idx_max[0], :]
            )  # A non-flat threshold can move a peak slightly
            i_speed = get_interpolated_fft_peak_index(fftframe[:, idx_max[1]], int(idx_max[0]))

            distance = (
                APPROX_BASE_STEP_LENGTH_M
                * (
                    self.sensor_config.start_point
                    + self.filt_margin * self.sensor_config.step_length
                    + self.sensor_config.step_length * i_dist
                )
                - self.offset_m
            )

            v = ((i_speed + spf / 2) % spf - spf / 2) * self.dv

            if 0 < idx_max[1] < (diff.shape[1] - 1):  # Disregard peaks at the limit of the range
                strength = _convert_amplitude_to_strength(
                    self.sensor_config.subsweeps[0],
                    abs_fftframe[idx_max[0], idx_max[1]],
                    distance,
                    bg_noise_stds[idx_max[1]],
                )
                targets.append(Target(distance=distance, velocity=v, strength=strength))

            abs_fftframe = subtract_reflector_from_fftmap(
                abs_fftframe, int(idx_max[1]), int(idx_max[0]), int(self.fwhm_points)
            )
            diff = abs_fftframe - fft_map_threshold

        er = SubsweepProcessorExtraResult(
            fft_map=abs_fftframe_extra, fft_map_threshold=fft_map_threshold, r=self.r
        )

        return SubsweepProcessorResult(targets=targets, extra_result=er)

    def apply_depth_filter(self, frame: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        # Written as a separate function to be callable during detector calibration

        filtered_array = np.array(filtfilt(self.b, self.a, frame), dtype=complex)
        cropped_array = filtered_array[:, self.filt_margin : -self.filt_margin]
        return cropped_array

    def update_config(self, config: ProcessorConfig) -> None:
        pass


class Processor(ProcessorBase[ProcessorResult]):
    """Obstacle processor

    :param sensor_config: Sensor configuration
    :param processor_config: Processor configuration
    :param context: Processor context
    """

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        processor_config: ProcessorConfig,
        context: ProcessorContext,
    ) -> None:
        self.sensor_config = sensor_config
        self.processor_config = processor_config

        self.num_subsweeps = sensor_config.num_subsweeps

        self.subsweep_processors: List[SubsweepProcessor] = []

        for i in range(self.num_subsweeps):
            subsweep_sensor_config_dict = sensor_config.to_dict()
            subsweep_sensor_config_dict["subsweeps"] = [sensor_config.subsweeps[i]]
            subsweep_sensor_config = a121.SensorConfig(**subsweep_sensor_config_dict)

            sspc = SubsweepProcessorContext(sub_sweep_idx=i)

            self.subsweep_processors.append(
                SubsweepProcessor(
                    sensor_config=subsweep_sensor_config,
                    processor_config=processor_config,
                    proc_context=context,
                    ssproc_context=sspc,
                )
            )

        # Calbration result
        self.true_zero_dist_idx = 0
        self.calbration_temperature = None

        self.filtered_sensor_temperature: Optional[float] = None
        self.temperature_filter_factor: float = 1 - np.exp(-TEMPERATURE_FILTER_CONSTANT)

        if self.sensor_config.sweep_rate is None:
            msg = "The obstacle detector needs the sweep_rate set."
            raise ValueError(msg)

        self.dv = (
            PERCEIVED_WAVELENGTH
            / 2
            / self.sensor_config.sweeps_per_frame
            * self.sensor_config.sweep_rate
        )

        self.kalman_filters: list[_KalmanFilter] = []
        self.update_rate = context.update_rate
        self.num_dead_reckoning_frames = int(
            processor_config.dead_reckoning_duration_s * self.update_rate
        )
        self.process_noise_gain_sensitivity = processor_config.sensitivity
        self.min_num_updates_valid_estimate = int(
            2 + (1 - self.process_noise_gain_sensitivity) * 20
        )

        # Largest anticipated distance change of target between frames. 4 to add margin.
        self.max_meas_state_diff_m = processor_config.max_robot_speed / self.update_rate * 4
        self.max_robot_speed = processor_config.max_robot_speed

    def process(self, result: a121.Result) -> ProcessorResult:
        # Filter temperature
        if self.filtered_sensor_temperature is None:
            self.filtered_sensor_temperature = float(result.temperature)
        else:
            self.filtered_sensor_temperature *= self.temperature_filter_factor
            self.filtered_sensor_temperature += (
                1 - self.temperature_filter_factor
            ) * result.temperature

        subsweep_results = [
            proc.process(subframe, temperature=self.filtered_sensor_temperature)
            for subframe, proc in zip(result.subframes, self.subsweep_processors)
        ]

        merged_targets = self._merge_subsweep_targets(subsweep_results)
        sorted_targets = self._sort_targets(
            merged_targets, self.processor_config.peak_sorting_method
        )

        # Update kalman filters.
        target_distances = [target.distance for target in sorted_targets]
        target_velocities = [target.velocity for target in sorted_targets]
        self.kalman_filters = self._update_kalman_filters(
            self.kalman_filters, target_distances, target_velocities
        )

        filtered_targets = []
        for target, kf in zip(sorted_targets, self.kalman_filters):
            distance = kf.get_distance()
            velocity = kf.get_velocity()
            new_target = Target(distance=distance, velocity=velocity, strength=target.strength)
            filtered_targets.append(new_target)

        subweeps_extra_results = [res.extra_result for res in subsweep_results]

        er = ProcessorExtraResult(dv=self.dv)

        return ProcessorResult(
            targets=filtered_targets,
            time=result.tick_time,
            extra_result=er,
            subsweeps_extra_results=subweeps_extra_results,
        )

    def _merge_subsweep_targets(
        self, subsweep_results: List[SubsweepProcessorResult]
    ) -> List[Target]:
        # The same object can be seen at multiple subsweeps, objects close can be mereged.

        all_targets = [target for sr in subsweep_results for target in sr.targets]

        while True:
            closest_dist = 2.0  # Initialized to larger than one
            for i in range(len(all_targets)):
                for j in range(i):
                    d = (
                        (all_targets[i].velocity - all_targets[j].velocity) / MERGE_SPEED_MPS
                    ) ** 2
                    d += (
                        (all_targets[i].distance - all_targets[j].distance) / MERGE_DISTANCE_M
                    ) ** 2

                    if d < closest_dist:
                        closest_dist = d
                        ij = (i, j)

            if closest_dist < 1.0:
                t1 = all_targets[ij[0]]
                t2 = all_targets[ij[1]]
                all_targets.append(
                    Target(
                        distance=(t1.distance + t2.distance) / 2,
                        velocity=(t1.velocity + t2.velocity) / 2,
                        strength=(t1.strength + t2.strength) / 2,
                    )
                )

                all_targets.remove(t1)
                all_targets.remove(t2)

            else:
                break

        return all_targets

    def apply_depth_filter(self, result: a121.Result) -> list[npt.NDArray[np.complex128]]:
        return [
            ssp.apply_depth_filter(r) for r, ssp in zip(result.subframes, self.subsweep_processors)
        ]

    def update_config(self, config: ProcessorConfig) -> None:
        pass

    @staticmethod
    def _sort_targets(
        targets: List[Target],
        method: PeakSortingMethod,
    ) -> List[Target]:
        if method == PeakSortingMethod.CLOSEST:
            quantity_to_sort = np.array([target.distance for target in targets])
        elif method == PeakSortingMethod.STRONGEST:
            quantity_to_sort = np.array([-target.strength for target in targets])
        else:
            msg = "Unknown peak sorting method"
            raise ValueError(msg)

        return [targets[i] for i in quantity_to_sort.argsort()]

    def get_closest_target_index(
        self,
        distances: npt.NDArray[np.float64],
        velocities: npt.NDArray[np.float64],
        kf_distance: float,
        kf_velocity: float,
    ) -> int:
        cost = np.sqrt(
            np.square((velocities - kf_velocity) / self.max_robot_speed)
            + np.square((distances - kf_distance) / self.max_meas_state_diff_m)
        )
        index = int(np.argmin(cost))

        return index

    def _update_kalman_filters(
        self,
        kfs: List[_KalmanFilter],
        distances: List[float],
        velocities: List[float],
    ) -> List[_KalmanFilter]:
        """Update Kalman filters for a sensor, using new distance and velocity estimates.
        Identifying the target, based on distance and velocity, closest to the current state of the filter.
        If the target is sufficiently close to the current state, it is used to update the filter.
        Once a target has been used to update a filter, it can't be used by other filters.
        If no estimated target matches the filter, dead reckoning is used. Each time dead
        reckoning is performed, a counter is incremented. If the counter exceeds a certain value,
        the filter is deleted.
        A filter must have a minimum number of updates before it is regarded as initiated.
        """
        distances = copy.deepcopy(list(distances))
        velocities = copy.deepcopy(list(velocities))
        kfs = copy.deepcopy(kfs)
        for kf in kfs:
            # Find the indexes of the closest distances.
            state_vs_distance_diff = np.abs(np.array(kf.get_distance()) - np.array(distances))
            idxs_close_to_estimate = np.where(state_vs_distance_diff < self.max_meas_state_diff_m)[
                0
            ]
            kf.predict()
            if len(distances) == 0 or len(idxs_close_to_estimate) == 0:
                # No estimates found.
                kf.dead_reckoning_count += 1
                # Remove the filter if not initialized or number of dead reckoning steps is to
                # high.
                if self.num_dead_reckoning_frames < kf.dead_reckoning_count or not kf.has_init:
                    kfs.remove(kf)
            else:
                # Estimates found.
                kf.dead_reckoning_count = 0
                # Find the target closest to the current estimates.
                distances_array = np.asarray(distances)
                velocities_array = np.asarray(velocities)
                idx_closest = self.get_closest_target_index(
                    distances_array[idxs_close_to_estimate],
                    velocities_array[idxs_close_to_estimate],
                    kf.get_distance(),
                    kf.get_velocity(),
                )
                idx_in_r_array = idxs_close_to_estimate[idx_closest]
                # Update KF
                kf.update(np.matrix([[distances[idx_in_r_array]], [velocities[idx_in_r_array]]]))
                # Remove distance and velocity as they have now been used to update a filter.
                distances.pop(idx_in_r_array)
                velocities.pop(idx_in_r_array)
                # Check if the minimum number of updates have been reached. If so, the filter has
                # been initialized.
                if self.min_num_updates_valid_estimate <= kf.num_updates:
                    kf.has_init = True
        for distance, velocity in zip(distances, velocities):
            kfs.append(
                _KalmanFilter(
                    1 / self.update_rate,
                    self.process_noise_gain_sensitivity,
                    distance,
                    velocity,
                    self.min_num_updates_valid_estimate,
                )
            )
        return kfs


def apply_max_depth_filter(
    abs_sweep: npt.NDArray[np.float64], config: a121.SubsweepConfig
) -> npt.NDArray[np.float64]:
    """Filter sweep so that every point is max within +/- one fwhm"""

    filtered_sweep = np.zeros_like(abs_sweep)

    half_max_length_idx = int(
        ENVELOPE_FWHM_M[config.profile] / (APPROX_BASE_STEP_LENGTH_M * config.step_length)
    )

    for i, _ in enumerate(abs_sweep):
        filtered_sweep[i] = np.max(
            abs_sweep[
                max(0, i - half_max_length_idx) : min(i + half_max_length_idx, len(abs_sweep))
            ]
        )

    return filtered_sweep


def get_interpolated_range_peak_index(env: npt.NDArray[np.float64]) -> float:
    """Simple quadratic peak interpolation assuming equidistant points"""

    SMALL_NUMBER = 1e-10  # To avoid divide by zero for a flat peak.

    i = int(np.argmax(env))

    if i == 0 or i == len(env) - 1:
        return i

    return float(
        i
        + (env[i + 1] - env[i - 1]) / (4 * env[i] - 2 * env[i - 1] - 2 * env[i + 1] + SMALL_NUMBER)
    )


def get_interpolated_fft_peak_index(Y: npt.NDArray[np.complex128], idx: int) -> float:
    """FFT peak interpolation according to Quinn's method"""

    Y2 = np.abs(Y[idx]) ** 2
    idxp1 = (idx + 1) % len(Y)
    ap = (Y[idxp1].real * Y[idx].real + Y[idxp1].imag * Y[idx].imag) / Y2
    dp = -ap / (1.0 - ap)
    am = (Y[idx - 1].real * Y[idx].real + Y[idx - 1].imag * Y[idx].imag) / Y2
    dm = am / (1.0 - am)

    return float(idx + (dp if ((dp > 0) & (dm > 0)) else dm))


def subtract_reflector_from_fftmap(
    fftmap: npt.NDArray[np.float64], r_idx: int, f_idx: int, fwhm: float
) -> npt.NDArray[np.float64]:
    """Subtract signal from single reflector in fft map"""

    MARGIN_FACTOR = 2

    Nf, Nr = fftmap.shape
    map_range = np.clip(
        1 - np.abs(np.arange(Nr) - r_idx) / (MARGIN_FACTOR * fwhm), 0, np.inf
    )  # Triangular envelope

    fs = np.arange(Nf)
    map_freq = np.sum([1 / (np.abs(f_idx + d * Nf - fs) + 1) for d in [-1, 0, 1]])

    peak = fftmap[f_idx, r_idx]

    return np.array(
        np.clip(
            fftmap - MARGIN_FACTOR * peak * np.outer(map_freq / np.max(map_freq), map_range),
            0,
            np.inf,
        )
    )


class _KalmanFilter:
    # Acceleration noise std (m/s^2).
    _PROCESS_NOISE_STD = 0.01
    # Distance estimated noise std (m).
    _MEASUREMENT_NOISE_STD = 0.005

    def __init__(
        self,
        dt: float,
        process_noise_gain_sensitivity: float,
        init_position: float,
        init_velocity: float,
        min_num_updates_valid_estimate: int,
    ) -> None:
        self.A: npt.NDArray[np.float64] = np.matrix([[1.0, dt], [0.0, 1.0]])
        self.H: npt.NDArray[np.float64] = np.matrix([[1, 0], [0, 1]])
        process_noise_gain = self._sensitivity_to_gain(process_noise_gain_sensitivity)
        # Random acceleration process noise.
        self.Q = (
            np.matrix([[(dt**4) / 4, (dt**3) / 2], [(dt**3) / 2, dt**2]])
            * (self._PROCESS_NOISE_STD) ** 2
            * process_noise_gain
        )
        self.R = self._MEASUREMENT_NOISE_STD**2
        self.P = np.eye(self.A.shape[1])
        self.x: npt.NDArray[np.float64] = np.matrix([[init_position], [init_velocity]])
        self.min_num_updates_valid_estimate = min_num_updates_valid_estimate
        self.dead_reckoning_count = 0
        self.num_updates = 0
        self.has_init = False

    def predict(self) -> None:
        self.x = np.dot(self.A, self.x)
        self.P = np.dot(np.dot(self.A, self.P), self.A.T) + self.Q

    def update(self, z: npt.NDArray[np.float64]) -> None:
        S = np.dot(self.H, np.dot(self.P, self.H.T)) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        self.x = self.x + np.dot(K, (z - np.dot(self.H, self.x)))
        I = np.eye(self.H.shape[1])
        self.P = (I - (K * self.H)) * self.P
        self.num_updates += 1
        if self.min_num_updates_valid_estimate < self.num_updates:
            self.has_init = True

    def get_distance(self) -> float:
        return float(self.x[0, 0])

    def get_velocity(self) -> float:
        return float(self.x[1, 0])

    @staticmethod
    def _sensitivity_to_gain(sensitivity: float) -> float:
        return 0.01 + sensitivity * 20.0
