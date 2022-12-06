# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import copy
import typing as t

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoProcessorConfigBase
from acconeer.exptool.a121.algo.distance import DetectorResult


@attrs.frozen(kw_only=True)
class Point:
    """A point located in the 2D plane spanned by the two sensors."""

    angle: float
    distance: float
    x_coord: float
    y_coord: float


@attrs.frozen(kw_only=True)
class ObjectWithoutCounterpart:
    """Object that was not matched with distance from other sensor."""

    distance: float
    sensor_position: str


@attrs.frozen(kw_only=True)
class _KalmanFilterResult:
    """Result from a Kalman filter."""

    distance: float
    sensor_position: str


@attrs.frozen(kw_only=True)
class ProcessorResult:
    """Processor result"""

    points: t.List[Point]
    objects_without_counterpart: t.List[ObjectWithoutCounterpart]


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):
    sensor_spacing_m: float = attrs.field(default=0.1)
    """Distance between the two sensors (m) in the intended installation."""
    max_anticipated_velocity_mps: float = attrs.field(default=2.0)
    """Specify the highest anticipated radial velocity between sensors/device and
    objects (m/s)."""
    dead_reckoning_duration_s: float = attrs.field(default=0.5)
    """Specify the duration (s) of the Kalman filter to perform dead reckoning before stop
    tracking."""
    sensitivity: float = attrs.field(default=0.5)
    """Specify the sensitivity of the Kalman filter. A higher value yields a more responsive
    filter. A lower value yields a more robust filter."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.update_rate is None:
            validation_results.append(
                a121.ValidationError(
                    config,
                    "update_rate",
                    "Must be set",
                )
            )

        return validation_results


class Processor:
    """Bilateration processor
    :param sensor_config: Sensor configuration.
    :param extended_metadata: Metadata yielded by the sensor config.
    :param processor_config: Processor configuration.
    :param sensor_ids: Sensor IDs used.
    """

    _SENSOR_POSITION_LEFT = "left"
    _SENSOR_POSITION_RIGHT = "right"
    _MAX_NUM_OBJECTS = 10

    def __init__(
        self,
        session_config: a121.SessionConfig,
        processor_config: ProcessorConfig,
        sensor_ids: t.List[int],
    ):
        if len(sensor_ids) != 2:
            raise ValueError("Number of sensor ids must equal two.")
        processor_config.validate(session_config)
        assert session_config.update_rate is not None  # Should never happen, checked in validate
        self.update_rate = session_config.update_rate
        self.sensor_spacing_m = processor_config.sensor_spacing_m
        self.process_noise_gain_sensitivity = processor_config.sensitivity
        self.num_dead_reckoning_frames = int(
            processor_config.dead_reckoning_duration_s * self.update_rate
        )
        # Largest anticipated distance change of target between frames. 4 to add margin.
        self.max_meas_state_diff_m = (
            processor_config.max_anticipated_velocity_mps / self.update_rate * 4
        )
        self.min_num_updates_valid_estimate = self._sensitivity_to_min_num_updates_for_tracking(
            processor_config.sensitivity
        )
        self.sensor_position_to_ids = {
            self._SENSOR_POSITION_LEFT: sensor_ids[0],
            self._SENSOR_POSITION_RIGHT: sensor_ids[1],
        }
        self.left_sensor_kfs: list[_KalmanFilter] = []
        self.right_sensor_kfs: list[_KalmanFilter] = []

    def process(self, result: t.Dict[int, DetectorResult]) -> ProcessorResult:
        distances_left = result[self.sensor_position_to_ids[self._SENSOR_POSITION_LEFT]].distances
        rcs_left = result[self.sensor_position_to_ids[self._SENSOR_POSITION_LEFT]].rcs
        distances_right = result[
            self.sensor_position_to_ids[self._SENSOR_POSITION_RIGHT]
        ].distances
        rcs_right = result[self.sensor_position_to_ids[self._SENSOR_POSITION_RIGHT]].rcs
        assert distances_left is not None
        assert rcs_left is not None
        assert distances_right is not None
        assert rcs_right is not None
        # Get distances from detector result and remove closely spaced distances.
        distances_left_cleaned = self._remove_closely_spaced_distances(
            distances_left,
            rcs_left,
            self.sensor_spacing_m,
        )
        distances_right_cleaned = self._remove_closely_spaced_distances(
            distances_right,
            rcs_right,
            self.sensor_spacing_m,
        )
        # Truncate list to a known max length.
        if self._MAX_NUM_OBJECTS < len(distances_left_cleaned):
            distances_left_cleaned = distances_left_cleaned[self._MAX_NUM_OBJECTS :]
        if self._MAX_NUM_OBJECTS < len(distances_right_cleaned):
            distances_right_cleaned = distances_right_cleaned[self._MAX_NUM_OBJECTS :]
        # Update kalman filters.
        self.left_sensor_kfs = self._update_kalman_filters(
            self.left_sensor_kfs, distances_left_cleaned, self._SENSOR_POSITION_LEFT
        )
        self.right_sensor_kfs = self._update_kalman_filters(
            self.right_sensor_kfs,
            distances_right_cleaned,
            self._SENSOR_POSITION_RIGHT,
        )
        # Extract result after filtering.
        kf_result_left_sensor = [
            _KalmanFilterResult(distance=kf.get_distance(), sensor_position=kf.sensor_position)
            for kf in self.left_sensor_kfs
            if kf.has_init
        ]
        kf_result_right_sensor = [
            _KalmanFilterResult(distance=kf.get_distance(), sensor_position=kf.sensor_position)
            for kf in self.right_sensor_kfs
            if kf.has_init
        ]
        # Match result from both sensors to create pairs and objects without counterpart.
        (points, objects_without_counterpart) = self._pair_distances(
            kf_result_left_sensor, kf_result_right_sensor, self.sensor_spacing_m
        )
        return ProcessorResult(
            points=points, objects_without_counterpart=objects_without_counterpart
        )

    def _pair_distances(
        self,
        kf_result_left_sensor: t.List[_KalmanFilterResult],
        kf_result_right_sensor: t.List[_KalmanFilterResult],
        sensor_spacing: float,
    ) -> t.Tuple[t.List[Point], t.List[ObjectWithoutCounterpart]]:
        """Pair distance from each sensor to form points.
        The sensor with the least number of results is identified and looped over. In each loop,
        the distance is matched to a distance from the other sensor. The condition for a match is
        the absolute distance difference being lower than the sensor spacing.
        A distance can only be matched once. When matched, it is marked and can not be
        matched other distances.
        Each pair is used to form a point, for which the distance and angle is calculated, along
        with its cartesian coordinates.
        Distances without a pair is regarded as an object without a counterpart.

        The bilateration function expects the distance estimate from the left sensor as the first
        argmument. If the value from the right sensor is fed as the first element, the sign of the
        angle needs to be flipped.
        """
        if len(kf_result_left_sensor) <= len(kf_result_right_sensor):
            shorter_result = kf_result_left_sensor
            longer_result = kf_result_right_sensor
            flip_angle = False
        else:
            shorter_result = kf_result_right_sensor
            longer_result = kf_result_left_sensor
            flip_angle = True

        shorter_result_item_has_pair = [False] * len(shorter_result)
        longer_result_item_has_pair = [False] * len(longer_result)
        distances_longer_result = np.array([kf_result.distance for kf_result in longer_result])
        points = []
        for kf_idx, kf_shorter in enumerate(shorter_result):
            # Find the closest distance in the other array
            idx_closest = np.argmin(np.abs(kf_shorter.distance - distances_longer_result))
            # Add as a pair, if the distance is within the expected range(plus a small margin).
            if np.abs(kf_shorter.distance - distances_longer_result[idx_closest]) < sensor_spacing:
                distance = (kf_shorter.distance + distances_longer_result[idx_closest]) / 2

                angle = self._estimate_angle(
                    kf_shorter.distance, distances_longer_result[idx_closest], sensor_spacing
                )

                if flip_angle:
                    angle = -angle

                points.append(
                    Point(
                        angle=angle,
                        distance=distance,
                        x_coord=np.sin(angle) * distance,
                        y_coord=np.cos(angle) * distance,
                    )
                )
                shorter_result_item_has_pair[kf_idx] = True
                longer_result_item_has_pair[idx_closest] = True
        objects_without_counterpart = []
        for i in [i for i, has_init in enumerate(shorter_result_item_has_pair) if not has_init]:
            objects_without_counterpart.append(
                ObjectWithoutCounterpart(
                    distance=shorter_result[i].distance,
                    sensor_position=shorter_result[i].sensor_position,
                )
            )
        for i in [i for i, has_init in enumerate(longer_result_item_has_pair) if not has_init]:
            objects_without_counterpart.append(
                ObjectWithoutCounterpart(
                    distance=longer_result[i].distance,
                    sensor_position=longer_result[i].sensor_position,
                )
            )
        return (points, objects_without_counterpart)

    @staticmethod
    def _remove_closely_spaced_distances(
        distances: npt.NDArray[np.float_], rcs: npt.NDArray[np.float_], min_dist: float
    ) -> t.List[float]:
        """Remove closely spaced distances to avoid ambiguity in later filtering and distance
        pairing stages.
        If two distance are closely spaced, keep the one with highest RCS.
        """
        if len(distances) == 0:
            return []
        # Sort according to distance.
        distances, rcs = zip(*sorted(zip(distances, rcs)))
        # If two distance are closer than the senor spacing, remove the one with smaller amplitude.
        index_closely_spaced_distances = np.where(np.abs(np.diff(distances)) < min_dist)[0]
        # Flip the array of indexes to avoid altering the order of the elements to the left in
        # the array.
        for index in np.flip(index_closely_spaced_distances):
            # Remove the element with the lower amplitude.
            if rcs[index] < rcs[index + 1]:
                rcs = np.delete(rcs, index)
                distances = np.delete(distances, index)
            else:
                rcs = np.delete(rcs, index + 1)
                distances = np.delete(distances, index + 1)
        return list(distances)

    def _update_kalman_filters(
        self,
        kfs: t.List[_KalmanFilter],
        distances: t.List[float],
        sensor_position: str,
    ) -> t.List[_KalmanFilter]:
        """Update Kalman filters for a sensor, using new distance estimates.
        Identifying the distance closest to the current state of the filter. If the distance is
        sufficiently close to the current state, it is used to update the filter. Once a distance
        has been used to update a filter, it can't be used by other filters.
        If no estimated distance matches the filter, dead reckoning is used. Each time dead
        reckoning is performed, a counter is incremented. If the counter exceeds a certain value,
        the filter is deleted.
        A filter must have a minimum number of updates before it is regarded as initiated and used
        for bilateration in a subsequent steps.
        """
        distances = copy.deepcopy(list(distances))
        kfs = copy.deepcopy(kfs)
        for kf in kfs:
            # Find the index of the closest distance.
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
                if (
                    self.num_dead_reckoning_frames < kf.dead_reckoning_count
                    or kf.num_updates < self.num_dead_reckoning_frames - 1
                ):
                    kfs.remove(kf)
            else:
                # Estimates found.
                kf.dead_reckoning_count = 0
                # Find the point in the data closest to the current estimated distance.
                idx_closest = np.argmin(state_vs_distance_diff[idxs_close_to_estimate])
                idx_in_r_array = idxs_close_to_estimate[idx_closest]
                # Update KF
                kf.update(distances[idx_in_r_array])
                # Remove distance as it has now been used to update a filter.
                distances.pop(idx_in_r_array)
                # Check if the minimum number of updates have been reached. If so, the filter has
                # been initialized.
                if self.min_num_updates_valid_estimate <= kf.num_updates:
                    kf.has_init = True
        for distance in distances:
            kfs.append(
                _KalmanFilter(
                    1 / self.update_rate,
                    self.process_noise_gain_sensitivity,
                    distance,
                    sensor_position,
                    self.min_num_updates_valid_estimate,
                )
            )
        return kfs

    @staticmethod
    def _estimate_angle(
        left_sensor: float, right_sensor: float, sensor_spacing: float
    ) -> float | t.Any:
        """Calculates the angle to an object given two distance values. The first argument should
        reflect the value at the left sensor(left from the perspective of the sensor, facing
        forward). The second argument should reflect the value of the right sensor."""
        if sensor_spacing < np.abs(left_sensor - right_sensor):
            return np.nan
        x0 = left_sensor**2 - right_sensor**2
        x1 = np.sqrt(
            2 * sensor_spacing**2 * (left_sensor**2 + right_sensor**2)
            - (left_sensor**2 - right_sensor**2) ** 2
            - sensor_spacing**4 / 2
        )
        return np.arctan(x0 / x1)

    @staticmethod
    def _sensitivity_to_min_num_updates_for_tracking(sensitivity: float) -> int:
        return int(2 + (1 - sensitivity) * 20)


class _KalmanFilter:
    # Acceleration noise std (m/s^2).
    _PROCESS_NOISE_STD = 0.01
    # Distance estimated noise std (m).
    _MEASUREMENT_NOISE_STD = 0.005

    def __init__(
        self,
        dt: float,
        process_noise_gain_sensitivity: float,
        init_state: float,
        sensor_position: str,
        min_num_updates_valid_estimate: int,
    ) -> None:
        self.A = np.matrix([[1.0, dt], [0.0, 1.0]])
        self.H = np.matrix([[1, 0]])
        process_noise_gain = self._sensitivity_to_gain(process_noise_gain_sensitivity)
        # Random acceleration process noise.
        self.Q = (
            np.matrix([[(dt**4) / 4, (dt**3) / 2], [(dt**3) / 2, dt**2]])
            * (self._PROCESS_NOISE_STD) ** 2
            * process_noise_gain
        )
        self.R = self._MEASUREMENT_NOISE_STD**2
        self.P = np.eye(self.A.shape[1])
        self.x = np.matrix([[init_state], [0.0]])
        self.min_num_updates_valid_estimate = min_num_updates_valid_estimate
        self.dead_reckoning_count = 0
        self.num_updates = 0
        self.sensor_position = sensor_position
        self.has_init = False

    def predict(self) -> None:
        self.x = np.dot(self.A, self.x)
        self.P = np.dot(np.dot(self.A, self.P), self.A.T) + self.Q

    def update(self, z: float) -> None:
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

    @staticmethod
    def _sensitivity_to_gain(sensitivity: float) -> float:
        return 0.01 + sensitivity * 20.0
