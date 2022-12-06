# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import enum
from typing import Optional

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoParamEnum, AlgoProcessorConfigBase, ProcessorBase


class MeasurementType(AlgoParamEnum):
    CLOSE_RANGE = enum.auto()
    FAR_RANGE = enum.auto()
    CLOSE_AND_FAR_RANGE = enum.auto()


@attrs.mutable(kw_only=True)
class ProcessorConfig(AlgoProcessorConfigBase):

    measurement_type: MeasurementType = attrs.field(
        default=MeasurementType.CLOSE_RANGE,
        converter=MeasurementType,
    )
    """The measurement type.
    ``CLOSE_RANGE`` corresponds to a range of approximate 2 cm - 12 cm.
    ``FAR_RANGE`` corresponds to approximate 10 cm - 30 cm.
    ``CLOSE_AND_FAR_RANGE`` gives two detection outputs, one for each range."""

    sensitivity_close: float = attrs.field(default=1.9)
    """Sensitivity for close range detection. High sensitivity equals low detection threshold,
    low sensitivity equals high detection threshold."""

    sensitivity_far: float = attrs.field(default=2.0)
    """Sensitivity for far range detection. High sensitivity equals low detection threshold,
    low sensitivity equals high detection threshold."""

    patience_close: int = attrs.field(default=2)
    """Number of frames in a row above threshold to count as a new close range detection,
    also number of frames in a row below threshold to count as end of detection."""

    patience_far: int = attrs.field(default=2)
    """Number of frames in a row above threshold to count as a new far range detection,
    also number of frames in a row below threshold to count as end of detection."""

    calibration_duration_s: float = attrs.field(default=0.6)
    """Calibration duration in seconds"""

    calibration_interval_s: float = attrs.field(default=20)
    """Interval between calibrations in seconds. When reached a new calibration is made.
    Should not be set lower than the longest estimated continuous detection event."""

    def _collect_validation_results(
        self, config: a121.SessionConfig
    ) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        if config.sensor_config.num_subsweeps > 2:
            validation_results.append(
                a121.ValidationError(
                    config.sensor_config,
                    "num_subsweeps",
                    "Number of subsweeps must be maximum 2",
                )
            )

        return validation_results


@attrs.frozen(kw_only=True)
class ProcessorResult:
    detection_close: Optional[bool] = attrs.field(default=None)
    detection_far: Optional[bool] = attrs.field(default=None)


class Processor(ProcessorBase[ProcessorConfig, ProcessorResult]):
    """Touchless Button processor

    :param sensor_config: Sensor configuration
    :param metadata: Metadata yielded by the sensor config
    :param processor_config: Processor configuration
    """

    def __init__(
        self,
        *,
        sensor_config: a121.SensorConfig,
        metadata: a121.Metadata,
        processor_config: ProcessorConfig,
    ) -> None:

        self._sensor_config = sensor_config
        self._metadata = metadata
        self._processor_config = processor_config

        self._processor_config.validate(self._sensor_config)

        self._sweeps_per_frame = sensor_config.sweeps_per_frame

        if sensor_config.sweep_rate is None:
            raise ValueError("sweep_rate must be set")

        frame_rate = sensor_config.sweep_rate / sensor_config.sweeps_per_frame
        self._cal_interval_frames = int(processor_config.calibration_interval_s * frame_rate)

        self._calibrate()

        self._detection_close = False
        self._detection_far = False

        self._sig_count = np.zeros((2,))
        self._nonsig_count = np.array(
            [processor_config.patience_close + 1, processor_config.patience_far + 1],
        )

    def process(self, result: a121.Result) -> ProcessorResult:
        frame = result.frame
        y = np.zeros_like(frame, dtype=float)

        sensitivity = self._get_sensitivity()

        if self._frames_since_last_cal > self._cal_interval_frames:
            self._calibrate()
        elif not np.any(np.isnan(self._cfar_ref_buf)):
            y = self._calc_variance(frame)

        significant = y > 1 / sensitivity * 10
        detection_depth, counts = np.unique(np.where(significant)[1], return_counts=True)

        if self._processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            self._detection_close = self._process_single_range(
                frame=frame,
                detection=self._detection_close,
                patience=self._processor_config.patience_close,
                detection_depth=detection_depth,
                counts=counts,
                measurement_type=MeasurementType.CLOSE_RANGE,
            )
            return ProcessorResult(detection_close=self._detection_close)

        if self._processor_config.measurement_type == MeasurementType.FAR_RANGE:
            self._detection_far = self._process_single_range(
                frame=frame,
                detection=self._detection_far,
                patience=self._processor_config.patience_far,
                detection_depth=detection_depth,
                counts=counts,
                measurement_type=MeasurementType.FAR_RANGE,
            )
            return ProcessorResult(detection_far=self._detection_far)

        if self._processor_config.measurement_type == MeasurementType.CLOSE_AND_FAR_RANGE:
            return self._process_multiple_ranges(
                frame=frame,
                detection_depth=detection_depth,
                counts=counts,
            )

        raise AssertionError

    def _calibrate(self) -> None:
        assert self._sensor_config.sweep_rate is not None
        self._cfar_ref_buf = np.full(
            (
                int(
                    self._processor_config.calibration_duration_s * self._sensor_config.sweep_rate
                ),
                self._metadata.sweep_data_length,
            ),
            np.nan,
            dtype="complex",
        )
        self._cfar_guard_buf = np.full(
            (self._sweeps_per_frame, self._metadata.sweep_data_length),
            np.nan,
            dtype="complex",
        )
        self._frames_since_last_cal = 0

    def _calc_variance(self, frame: npt.NDArray) -> npt.NDArray:
        xn = np.full((self._sweeps_per_frame, self._metadata.sweep_data_length), 0, dtype=float)
        y = np.full((self._sweeps_per_frame, self._metadata.sweep_data_length), 0, dtype=float)

        arg_norm = np.mean(self._cfar_ref_buf, axis=0)
        arg_norm = np.conj(arg_norm) / np.abs(arg_norm)

        arg_norm_ref = self._cfar_ref_buf * arg_norm
        ref_ampls = np.abs(arg_norm_ref)
        ampl_mean = np.mean(ref_ampls, axis=0)
        ampl_std = np.std(ref_ampls, axis=0)
        ref_phases = np.angle(arg_norm_ref)
        phase_mean = np.mean(ref_phases, axis=0)
        phase_std = np.std(ref_phases, axis=0)

        xn = frame * arg_norm

        y = np.hypot(
            (np.abs(xn) - ampl_mean) / ampl_std,
            (np.angle(xn) - phase_mean) / phase_std,
        )

        return y

    def _process_single_range(
        self,
        frame: npt.NDArray,
        detection: bool,
        patience: int,
        detection_depth: npt.NDArray,
        counts: npt.NDArray,
        measurement_type: MeasurementType,
    ) -> bool:

        if measurement_type == MeasurementType.CLOSE_RANGE:
            index = 0
        elif measurement_type == MeasurementType.FAR_RANGE:
            index = 1
        else:
            raise AssertionError

        # Checks if there are at least two significant values at the same depth
        if detection_depth[counts > 1].size > 0:
            self._sig_count[index] += 1
            self._nonsig_count[index] = 0
            self._cfar_guard_buf = np.full(
                (
                    self._sensor_config.sweeps_per_frame,
                    self._metadata.sweep_data_length,
                ),
                np.nan,
                dtype="complex",
            )
            self._frames_since_last_cal += 1
        else:
            self._sig_count[index] = 0
            self._nonsig_count[index] += 1

            if not np.isnan(self._cfar_guard_buf).any():
                self._update_cfar_buffer()

            self._cfar_guard_buf = frame

        detection = self._get_detection(
            detection,
            self._sig_count[index],
            self._nonsig_count[index],
            patience,
        )

        return detection

    def _process_multiple_ranges(
        self,
        frame: npt.NDArray,
        detection_depth: npt.NDArray,
        counts: npt.NDArray,
    ) -> ProcessorResult:

        if detection_depth[counts > 1].size > 0:
            if (
                np.where(
                    detection_depth[counts > 1] < self._sensor_config.subsweeps[0].num_points,
                    True,
                    False,
                )
            ).any():
                self._sig_count[0] += 1
                self._nonsig_count[0] = 0
            else:
                self._sig_count[0] = 0
                self._nonsig_count[0] += 1
            if (
                np.where(
                    detection_depth[counts > 1] >= self._sensor_config.subsweeps[0].num_points,
                    True,
                    False,
                )
            ).any():
                self._sig_count[1] += 1
                self._nonsig_count[1] = 0
            else:
                self._sig_count[1] = 0
                self._nonsig_count[1] += 1

            self._cfar_guard_buf = np.full(
                (
                    self._sensor_config.sweeps_per_frame,
                    self._metadata.sweep_data_length,
                ),
                np.nan,
                dtype="complex",
            )
            self._frames_since_last_cal += 1

        else:
            self._sig_count[0] = 0
            self._nonsig_count[0] += 1
            self._sig_count[1] = 0
            self._nonsig_count[1] += 1

            if not np.isnan(self._cfar_guard_buf).any():
                self._update_cfar_buffer()

            self._cfar_guard_buf = frame

        self._detection_close = self._get_detection(
            self._detection_close,
            self._sig_count[0],
            self._nonsig_count[0],
            self._processor_config.patience_close,
        )

        self._detection_far = self._get_detection(
            self._detection_far,
            self._sig_count[1],
            self._nonsig_count[1],
            self._processor_config.patience_far,
        )

        return ProcessorResult(
            detection_close=self._detection_close,
            detection_far=self._detection_far,
        )

    def _get_sensitivity(self) -> npt.NDArray[np.float_]:
        if self._processor_config.measurement_type == MeasurementType.FAR_RANGE:
            return np.repeat(
                self._processor_config.sensitivity_far,
                self._sensor_config.num_points,
            )
        elif self._processor_config.measurement_type == MeasurementType.CLOSE_RANGE:
            return np.repeat(
                self._processor_config.sensitivity_close,
                self._sensor_config.num_points,
            )
        elif self._processor_config.measurement_type == MeasurementType.CLOSE_AND_FAR_RANGE:
            return np.repeat(
                [
                    self._processor_config.sensitivity_close,
                    self._processor_config.sensitivity_far,
                ],
                [
                    self._sensor_config.subsweeps[0].num_points,
                    self._sensor_config.subsweeps[1].num_points,
                ],
            )

        raise AssertionError

    def _update_cfar_buffer(self) -> None:
        self._cfar_ref_buf = np.roll(self._cfar_ref_buf, -self._sweeps_per_frame, axis=0)
        self._cfar_ref_buf[-self._sweeps_per_frame :, :] = self._cfar_guard_buf
        self._frames_since_last_cal = 0

    @staticmethod
    def _get_detection(
        curr_detection: object, sig_count: int, nonsig_count: int, patience: int
    ) -> bool:
        new_detection = not curr_detection and sig_count >= patience
        keep_detection = curr_detection and nonsig_count <= patience
        detection = new_detection or keep_detection
        return bool(detection)

    def update_config(self, config: ProcessorConfig) -> None:
        raise NotImplementedError
