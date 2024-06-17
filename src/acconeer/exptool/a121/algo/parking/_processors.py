# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

from typing import Any, Dict, Tuple

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    exponential_smoothing_coefficient,
    get_distances_m,
    get_temperature_adjustment_factors,
)


MAX_AMPLITUDE = 46341  # sqrt((2^15)^2 + (2^15)^2)


@attrs.mutable(kw_only=True)
class ObstructionProcessorConfig:
    distance_threshold: float = attrs.field(default=0.1)
    """How far the weighted phase signature can be from calibration value and still be considered unobstructed."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []
        return validation_results


@attrs.frozen(kw_only=True)
class ObstructionProcessorExtraResult:
    obstruction_signature: npt.NDArray[np.float64] = attrs.field()
    """Signature of amplitudes used for the obstruction detection."""

    obstruction_data: npt.NDArray[np.float64] = attrs.field()
    """Array with obstruction amplitudes (usually direct leakage)."""

    obstruction_center: npt.NDArray[np.float64] = attrs.field()
    """Signature of amplitudes used in calibration."""

    obstruction_distance: float = attrs.field()
    """Distance threshold, same as in configuration."""


@attrs.mutable(kw_only=True)
class ObstructionProcessorResult:
    obstruction_found: bool = attrs.field(default=False)
    """Boolean indicating whether something is obstructing the sensor."""

    extra_result: ObstructionProcessorExtraResult = attrs.field(default=None)
    """Extra information for plotting."""


class ObstructionProcessor:
    # Cannot be ProcessorBase since the processor takes a frame instead of result
    def __init__(
        self,
        sensor_config: a121.SensorConfig,
        processor_config: ObstructionProcessorConfig,
        metadata: a121.Metadata,
        update_rate: float,
        calibration_center: npt.NDArray[np.float64],
        calibration_noise_mean: float,
        calibration_temperature: float,
    ):
        self.profile = sensor_config.profile
        self.processor_config = processor_config

        self.dist_thres = self.processor_config.distance_threshold

        self.distances = get_distances_m(sensor_config, metadata)

        self.x_dist_threshold, self.y_dist_threshold = self.get_thresholds(
            self.dist_thres, self.distances
        )

        self.calibration_noise_mean = calibration_noise_mean
        self.calibration_center = calibration_center
        self.calibration_temperature = calibration_temperature

        self.lp_signature = np.array(calibration_center)
        self.lp_const = exponential_smoothing_coefficient(
            update_rate, 0.8
        )  # 0.8 seconds to deal with noise jitter

    @staticmethod
    def get_thresholds(
        distance_threshold: float, distances: npt.NDArray[np.float64]
    ) -> Tuple[float, float]:
        distance_range = max(distances) - min(distances)

        x_width = distance_range * distance_threshold
        y_width = MAX_AMPLITUDE * distance_threshold

        return x_width, y_width

    @staticmethod
    def get_signature(
        frame: npt.NDArray[np.complex128], noise_level: float, distances: npt.NDArray[np.float64]
    ) -> Tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
        # Returns signature for a frame without temperature adjustment

        abs_frame = np.squeeze(abs(frame))
        noise_adjusted_frame = abs_frame - noise_level
        total_energy = np.sum(noise_adjusted_frame)
        avg_energy = total_energy / len(distances)
        weighted_sum = np.sum(distances * noise_adjusted_frame) / total_energy
        signature = np.array([weighted_sum, avg_energy])
        return signature, noise_adjusted_frame

    @staticmethod
    def get_noise_level(frame: npt.NDArray[np.complex128]) -> float:
        mean_frame = np.mean(frame, axis=0)
        abs_frame = abs(mean_frame)
        noise_level = float(np.mean(abs_frame))
        return noise_level

    def process(
        self, frame: npt.NDArray[np.complex128], temperature: float
    ) -> ObstructionProcessorResult:
        # Do temperature adjustment
        signal_adjustment_factor, deviation_adjustment_factor = get_temperature_adjustment_factors(
            reference_temperature=self.calibration_temperature,
            current_temperature=temperature,
            profile=self.profile,
        )

        # We could recalculate the level of the calibration frame as well.
        # That would be done by calibration_frame * signal_adjustment_factor
        temp_adjusted_frame = frame / signal_adjustment_factor

        noise_level = self.calibration_noise_mean * deviation_adjustment_factor

        signature, amp_adjusted = self.get_signature(
            temp_adjusted_frame, noise_level, self.distances
        )

        # low pass filtering to amend the noise jitter
        self.lp_signature = self.lp_signature * self.lp_const + (1.0 - self.lp_const) * signature

        dist_x = abs(self.lp_signature[0] - self.calibration_center[0])
        dist_y = abs(self.lp_signature[1] - self.calibration_center[1])

        obstructed = (dist_y > self.y_dist_threshold) or (dist_x > self.x_dist_threshold)

        extra_result = ObstructionProcessorExtraResult(
            obstruction_signature=self.lp_signature,
            obstruction_data=amp_adjusted,
            obstruction_center=self.calibration_center,
            obstruction_distance=self.dist_thres,
        )
        res = ObstructionProcessorResult(obstruction_found=obstructed, extra_result=extra_result)
        return res


@attrs.mutable(kw_only=True)
class ProcessorConfig:
    queue_length: int = attrs.field(default=5)
    """Number of samples above threshold to trigger parked car."""

    amplitude_threshold: float = attrs.field(default=15.0)
    """Threshold level in times the noise level to trigger."""

    weighted_distance_threshold_m: float = attrs.field(default=0.1)
    """Threshold in m between weighted distance points to consider them similar."""

    signature_similarity_threshold: float = attrs.field(default=0.6)
    """How large fraction of the signature history that has to be similar in order to retain detection."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []
        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorExtraResult:
    signature_history: npt.NDArray[np.float64] = attrs.field()
    """Array containing queue_length last signatures."""

    parking_data: npt.NDArray[np.float64] = attrs.field()
    """The scaled amplitude array used to calculate the last signature."""

    closest_observation: float = attrs.field()
    """If a car is detected, the distance to the weighted closest observation."""


@attrs.mutable(kw_only=True)
class ProcessorResult:
    car_detected: bool = attrs.field(default=False)
    """If a car (or other large object) is detected in front of the sensor."""

    extra_result: ProcessorExtraResult = attrs.field()
    """Extra information for plotting."""


class Processor:
    # Cannot be ProcessorBase since the processor takes a frame instead of result
    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        processor_config: ProcessorConfig,
        metadata: a121.Metadata,
        noise_estimate: float = 1.0,
        noise_estimate_temperature: float = 0.0,
    ):
        self.profile = sensor_config.profile
        self.distances = get_distances_m(sensor_config, metadata)
        if noise_estimate == 0.0:
            noise_estimate = 1.0
        self.noise_estimate = noise_estimate
        self.noise_estimate_temperature = noise_estimate_temperature

        self.norm_distances = self.distances / self.distances[0]

        self.frame_ind = 0

        # Thresholds
        self.weight_threshold = processor_config.amplitude_threshold
        self.distance_threshold = processor_config.weighted_distance_threshold_m
        self.similarity_threshold = processor_config.signature_similarity_threshold

        # signature history
        self.queue_length = processor_config.queue_length
        self.sig_history = np.zeros(
            self.queue_length,
            dtype=[("weighted_distance", float), ("max_energy", float)],
        )

    @classmethod
    def process_noise_frame(cls, frame: npt.NDArray[np.complex128]) -> float:
        n_std_dev = 2
        mean_frame = np.mean(frame, axis=0)
        amp = np.abs(mean_frame)
        dev = np.std(amp)
        noise_level = float(np.mean(amp) + n_std_dev * dev)
        return noise_level

    def signature(self, depths: npt.NDArray[np.float64]) -> Tuple[float, float]:
        total_energy = sum(depths)
        max_energy = max(depths)
        if total_energy != 0.0:
            weighted_distance = sum(depths * self.distances) / total_energy
        else:
            weighted_distance = self.distances[
                0
            ]  # We should return a distance, so pick the first.
        return (weighted_distance, max_energy)

    def objects_present(self) -> bool:
        energy_history = np.array([elm[1] for elm in self.sig_history])
        n_trigs = sum(energy_history > self.weight_threshold)
        ret = n_trigs > (self.queue_length * self.similarity_threshold)
        return ret

    def same_objects(self) -> Dict[str, Any]:
        depth_sigs = np.sort(self.sig_history, axis=0, order=["weighted_distance", "max_energy"])
        weights = np.array([elm[1] for elm in depth_sigs])
        depth_sigs = depth_sigs[weights > self.weight_threshold]

        clusters = []
        curr_cluster: list[Tuple[float, float]] = []
        for elm in depth_sigs:
            if len(curr_cluster) == 0:
                curr_cluster.append(elm)
            else:
                if (elm[0] - curr_cluster[0][0]) > self.distance_threshold:
                    clusters.append(curr_cluster)
                    curr_cluster = []
                else:
                    curr_cluster.append(elm)
        if len(curr_cluster) > 0:
            clusters.append(curr_cluster)

        if len(clusters) > 0:
            cluster_lengths = np.array([len(cluster) for cluster in clusters])
            long_cluster_ind = np.argmax(cluster_lengths)
            closest_dist = clusters[long_cluster_ind][0][0]
            similarity = max(cluster_lengths) / self.queue_length
            detection = similarity > self.similarity_threshold
        else:
            detection = False
            closest_dist = 0

        ret = {"detection": detection, "closest_dist": closest_dist}

        return ret

    def process(self, frame: npt.NDArray[np.complex128], temperature: float) -> ProcessorResult:
        self.frame_ind += 1

        _, deviation_adjustment_factor = get_temperature_adjustment_factors(
            reference_temperature=self.noise_estimate_temperature,
            current_temperature=temperature,
            profile=self.profile,
        )

        noise_level_adjusted = self.noise_estimate * deviation_adjustment_factor

        data = np.squeeze(frame, axis=0)  # remove sweep dimension

        # Div by zero avoided by tests elsewhere
        amp = np.squeeze(abs(data)) / noise_level_adjusted

        amp_noise_removed = np.fmax(amp - 1.0, 0)
        amp_scaled = amp_noise_removed * self.norm_distances

        sig = self.signature(amp_scaled)

        self.sig_history = np.roll(self.sig_history, -1, axis=0)
        self.sig_history[-1] = sig

        objects_present = self.objects_present()
        same_objects_info = self.same_objects()
        same_objects = same_objects_info["detection"]
        closest_object = same_objects_info["closest_dist"]

        parked_car = objects_present and same_objects

        extra_result = ProcessorExtraResult(
            signature_history=self.sig_history,
            parking_data=amp_scaled,
            closest_observation=closest_object,
        )

        ret = ProcessorResult(car_detected=parked_car, extra_result=extra_result)
        return ret
