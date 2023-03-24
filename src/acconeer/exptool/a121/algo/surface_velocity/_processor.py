# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple

import attrs
import numpy as np
import numpy.typing as npt
import scipy
from scipy.signal import welch

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._utils import PERCEIVED_WAVELENGTH, find_peaks, get_distances_m


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    surface_distance: float = attrs.field(default=1)
    sensor_angle: float = attrs.field(default=45)
    time_series_length: int = attrs.field(default=512)
    slow_zone: int = attrs.field(default=3)
    psd_lp_coeff: float = attrs.field(default=0.75)
    cfar_guard: int = attrs.field(default=6)
    cfar_win: int = attrs.field(default=6)
    cfar_sensitivity: float = attrs.field(default=0.15)
    velocity_lp_coeff: float = attrs.field(default=0.95)
    max_peak_interval_s: float = attrs.field(default=4)

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if len(config.sensor_config.subsweeps) > 1:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "subsweeps",
                    "Multiple subsweeps are not supported",
                )
            )

        if config.sensor_config.sweep_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "sweep_rate",
                    "Must be set",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorContext:
    ...


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    """
    Contains information for visualization in ET.
    """

    max_bin_vertical_vs: npt.NDArray[np.float_] = attrs.field()
    peak_width: float = attrs.field()

    vertical_velocities: npt.NDArray[np.float_] = attrs.field()
    psd: npt.NDArray[np.float_] = attrs.field()
    peak_idx: Optional[np.int_] = attrs.field()
    psd_threshold: npt.NDArray[np.float_] = attrs.field()


@attrs.frozen(kw_only=True)
class ProcessorResult:
    estimated_v: float = attrs.field()
    distance_m: float = attrs.field()

    extra_result: ProcessorExtraResult = attrs.field()


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):

    MIN_PEAK_VS = 0.1

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
        subsweep_index: Optional[int] = None,
        context: Optional[ProcessorContext] = None,
    ) -> None:
        if subsweep_index is None:
            subsweep_index = 0

        self.sensor_config = sensor_config
        self.metadata = metadata
        self.processor_config = processor_config
        self.subsweep_index = subsweep_index

        # Will never happen because checked in _collect_validation_results
        assert self.sensor_config.sweep_rate is not None

        self.sweep_rate = self.sensor_config.sweep_rate

        self.distances, _ = get_distances_m(self.sensor_config, metadata)
        self.num_distances = self.distances.size
        self.sweeps_per_frame = self.sensor_config.sweeps_per_frame

        if not sensor_config.continuous_sweep_mode:
            self.time_series_length = self.sweeps_per_frame
        else:
            if sensor_config.sweeps_per_frame > processor_config.time_series_length:
                raise ValueError("time_series_length must be >= sweeps_per_frame")

            self.time_series_length = processor_config.time_series_length

        self.time_series = np.zeros(
            [self.time_series_length, self.num_distances], dtype=np.complex_
        )

        self.surface_distance = processor_config.surface_distance
        self.sensor_angle = processor_config.sensor_angle

        if sensor_config.frame_rate is None:
            estimated_frame_rate = self.sweep_rate / self.sweeps_per_frame
        else:
            estimated_frame_rate = sensor_config.frame_rate

        self.max_peak_interval_n = processor_config.max_peak_interval_s * estimated_frame_rate

        # welch
        self.update_index = 0
        self.segment_length = self.time_series_length // 4
        if not np.mod(self.segment_length, 2) == 0:
            self.segment_length += 1

        self.middle_idx = int(np.around(self.segment_length / 2))

        _, bin_fs = self.scipy_welch(self.time_series, self.sweep_rate)
        self.bin_rad_vs = bin_fs * PERCEIVED_WAVELENGTH

        self.max_bin_vertical_vs = self.bin_rad_vs * self.get_angle_correction(self.distances[0])

        self.lp_velocity = 0.0

        self.lp_psds = np.zeros([self.segment_length, self.num_distances])
        self.psd_lp_coeff = processor_config.psd_lp_coeff

        # cfar
        self.cfar_guard_length = processor_config.cfar_guard
        self.cfar_win_length = processor_config.cfar_win

        if not processor_config.cfar_sensitivity > 0:
            raise ValueError("cfar_sensitivity must be > 0")

        self.cfar_sensitivity = processor_config.cfar_sensitivity

        self.slow_zone = processor_config.slow_zone
        self.velocity_lp_coeff = processor_config.velocity_lp_coeff

        self.wait_n = 0

        self.update_config(processor_config)

    @staticmethod
    def _dynamic_sf(static_sf: float, update_index: int) -> float:
        return min(static_sf, 1.0 - 1.0 / (1.0 + update_index))

    def scipy_welch(
        self, sweeps: npt.NDArray[np.complex_], sweep_rate: float
    ) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_]]:
        psds = []
        for i in np.arange(self.num_distances):
            freqs, psd = welch(
                x=sweeps[:, i],
                fs=sweep_rate,
                window="hann",
                nperseg=self.segment_length,
                noverlap=0,
                average="mean",
                axis=0,
                return_onesided=False,
            )
            freqs = scipy.fft.fftshift(freqs)
            psd = scipy.fft.fftshift(psd)
            psds.append(psd)

        return np.array(psds).T, freqs

    def get_angle_correction(self, distance: float) -> float:
        if (self.surface_distance / distance) < 1 and (self.surface_distance / distance) > -1:
            insonation_angle = np.arcsin(self.surface_distance / distance)
            angle_correction = 1 / np.cos(insonation_angle)
        else:
            angle_correction = 1

        return angle_correction  # type: ignore[no-any-return]

    def get_distance_idx(self, psds: npt.NDArray[np.float_]) -> int:
        max_negative_side = np.max(psds[self.middle_idx + self.slow_zone :, :], axis=0)
        max_positive_side = np.max(psds[: self.middle_idx - self.slow_zone, :], axis=0)
        max_amps = np.maximum(max_negative_side, max_positive_side)

        return np.argmax(max_amps, axis=0)  # type: ignore[no-any-return]

    def get_cfar_threshold(self, psd: npt.NDArray[np.float_]) -> npt.NDArray[np.float_]:
        window_length = self.cfar_win_length
        guard_length = self.cfar_guard_length
        margin = window_length + guard_length
        half_sweep_len_without_margin = int(np.around(psd.shape[0] / 2 - margin))
        min_psd = np.min(psd)

        # One-sided CFAR
        threshold_cfar = np.full(psd.shape, np.nan)
        filt_psd = np.convolve(psd, np.ones(window_length), "valid") / window_length
        threshold_cfar[margin : self.middle_idx] = filt_psd[:half_sweep_len_without_margin]
        threshold_cfar[self.middle_idx : -margin] = filt_psd[-half_sweep_len_without_margin:]

        threshold_cfar[:margin] = threshold_cfar[margin]
        threshold_cfar[-margin:] = threshold_cfar[-margin - 1]

        threshold_cfar += min_psd

        return threshold_cfar * 1 / self.cfar_sensitivity

    def cfar_peaks(
        self, threshold: npt.NDArray[np.float_], psd: npt.NDArray[np.float_]
    ) -> list[int]:
        return find_peaks(psd, threshold)

    @staticmethod
    def _merge_peaks(
        min_peak_to_peak_vel: float,
        velocities: npt.NDArray[np.float_],
        energies: npt.NDArray[np.float_],
    ) -> Tuple[npt.NDArray[np.float_], npt.NDArray[np.float_], npt.NDArray[np.float_]]:
        sorting_order = np.argsort(velocities)
        velocities_sorted = velocities[sorting_order]
        energies_sorted = energies[sorting_order]

        peak_cluster_idxs = np.where(min_peak_to_peak_vel < np.diff(velocities_sorted))[0] + 1
        velocities_merged = [
            np.mean(cluster)
            for cluster in np.split(velocities_sorted, peak_cluster_idxs)
            if velocities.size != 0
        ]

        velocities_width = [
            np.abs(np.max(cluster) - np.min(cluster))
            for cluster in np.split(velocities_sorted, peak_cluster_idxs)
            if velocities.size != 0
        ]

        energies_merged = [
            np.mean(cluster)
            for cluster in np.split(energies_sorted, peak_cluster_idxs)
            if velocities.size != 0
        ]

        return np.array(velocities_merged), np.array(velocities_width), np.array(energies_merged)

    def _get_peak_velocity(
        self,
        velocities: npt.NDArray[np.float_],
        energies: npt.NDArray[np.float_],
        bin_vs: npt.NDArray[np.float_],
    ) -> float:
        idxs = energies.argsort()
        slow_vs = []
        valid_vs = []
        for i in idxs:
            if np.abs(velocities[i]) < bin_vs[self.middle_idx + self.slow_zone]:
                slow_vs.append(velocities[i])
            else:
                valid_vs.append(velocities[i])

        if len(valid_vs) > 0:
            return valid_vs[-1]  # type: ignore[no-any-return]
        else:
            return slow_vs[-1]  # type: ignore[no-any-return]

    def get_velocity_estimate(
        self,
        bin_vertical_vs: npt.NDArray[np.float_],
        peak_idxs: list[int],
        psd: npt.NDArray[np.float_],
    ) -> Tuple[float, np.int_, float]:
        velocities, peak_widths, energies = self._merge_peaks(
            self.MIN_PEAK_VS, bin_vertical_vs[peak_idxs], psd[peak_idxs]
        )
        vertical_v = self._get_peak_velocity(velocities, energies, bin_vertical_vs)
        peak_width = peak_widths[np.nonzero(velocities == vertical_v)]
        peak_idx = np.argmin(np.abs(bin_vertical_vs - vertical_v))

        return vertical_v, peak_idx, peak_width[0]

    def get_velocity_estimate_slow_zone(
        self,
        bin_vertical_vs: npt.NDArray[np.float_],
        peak_idxs: list[int],
        psd: npt.NDArray[np.float_],
    ) -> Tuple[float, np.int_]:
        velocities = bin_vertical_vs[peak_idxs]
        energies = psd[peak_idxs]
        vertical_v = self._get_peak_velocity(velocities, energies, bin_vertical_vs)
        peak_idx = np.argmin(np.abs(bin_vertical_vs - vertical_v))

        return vertical_v, peak_idx

    def process(self, result: a121.Result) -> ProcessorResult:
        data_segment = result.subframes[self.subsweep_index]

        self.time_series = np.roll(self.time_series, axis=0, shift=-self.sweeps_per_frame)
        self.time_series[-self.sweeps_per_frame :, :] = data_segment

        psds, _ = self.scipy_welch(self.time_series, self.sweep_rate)
        if self.update_index * self.sweeps_per_frame < self.time_series_length:
            self.lp_psds = psds

        self.lp_psds = self.lp_psds * self.psd_lp_coeff + psds * (1 - self.psd_lp_coeff)

        distance_idx = self.get_distance_idx(self.lp_psds)
        self.distance_idx = distance_idx
        distance = self.distances[distance_idx]
        psd = self.lp_psds[:, distance_idx]
        bin_vertical_vs = self.bin_rad_vs * self.get_angle_correction(distance)

        psd_cfar = self.get_cfar_threshold(psd)
        psd_peak_idxs = self.cfar_peaks(psd_cfar, psd)

        if len(psd_peak_idxs) > 0:
            if np.max(np.abs(bin_vertical_vs[psd_peak_idxs])) > bin_vertical_vs[self.slow_zone]:
                vertical_v, peak_idx, peak_width = self.get_velocity_estimate(
                    bin_vertical_vs, psd_peak_idxs, psd
                )
            else:
                vertical_v, peak_idx = self.get_velocity_estimate_slow_zone(
                    bin_vertical_vs, psd_peak_idxs, psd
                )
                peak_width = 0

            if np.abs(self.lp_velocity) > 0 and vertical_v / self.lp_velocity < 0.8:
                if self.wait_n < self.max_peak_interval_n:
                    vertical_v = self.lp_velocity
                    self.wait_n += 1
            else:
                self.wait_n = 0

        else:
            if self.wait_n < self.max_peak_interval_n:
                vertical_v = self.lp_velocity
                self.wait_n += 1
            else:
                vertical_v = 0

            peak_idx = None
            peak_width = 0

        sf = self._dynamic_sf(self.velocity_lp_coeff, self.update_index)
        if (self.update_index * self.sweeps_per_frame) > self.time_series_length:
            self.lp_velocity = sf * self.lp_velocity + (1 - sf) * vertical_v

        self.update_index += 1

        extra_result = ProcessorExtraResult(
            max_bin_vertical_vs=self.max_bin_vertical_vs,
            peak_width=peak_width,
            vertical_velocities=bin_vertical_vs,
            psd=psd,
            peak_idx=peak_idx,
            psd_threshold=psd_cfar,
        )

        return ProcessorResult(
            estimated_v=self.lp_velocity,
            distance_m=distance,
            extra_result=extra_result,
        )

    def update_config(self, config: ProcessorConfig) -> None:
        ...
