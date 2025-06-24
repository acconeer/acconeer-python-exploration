# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import enum
from typing import Any, Optional, Tuple

import attrs
import h5py
import numpy as np
import numpy.typing as npt
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    AlgoConfigBase,
    Controller,
)
from acconeer.exptool.a121.algo.presence._processors import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
)


class DetectionState(enum.Enum):
    """Indicating the current detection state."""

    NO_DETECTION = enum.auto()
    """No detection."""

    DETECTION = enum.auto()
    """Detection."""

    RETENTION = enum.auto()
    """No detection. Retaining detection."""


@attributes_doc
@attrs.mutable(kw_only=True)
class ExampleAppConfig(AlgoConfigBase):
    # Setup parameters
    sensor_to_water_distance: float = attrs.field(default=0.12)
    """Distance from the sensor location to the center of the water jet (m)."""

    water_jet_width: float = attrs.field(default=0.02)
    """Water jet width (m).

    Defines the width of a region, centered around the water jet, where the hand motion is not
    analyzed, in order to exclude the water jet motion from the motion metric.
    """

    measurement_range_end: float = attrs.field(default=0.2)
    """Distance between sensor and end point of measurement range (m)."""

    # Filtering parameters
    filter_time_const: float = attrs.field(default=0.3)
    """Time constant of filter applied during processing.

    A lower value yield a more responsive algorithm. A higher value yield a more robust response.
    """

    threshold: float = attrs.field(default=1.5)
    """Threshold applied to the calculate metric.

    If the metric is above the threshold, a hand movement has been detected.
    """

    detection_retention_duration: float = attrs.field(default=1.0)
    """Detection retention duration (s).

    The detection will be kept as True for this duration, after detection is lost.
    """

    # Sensor config parameters
    hwaas: int = attrs.field(default=32)
    """HWAAS."""

    sweeps_per_frame: int = attrs.field(default=64)
    """Sweeps per frame."""

    sweeps_rate: int = attrs.field(default=1000)
    """Sweep rate."""

    frame_rate: int = attrs.field(default=10)
    """Frame rate."""

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        return validation_results


opser.register_json_presentable(ExampleAppConfig)


@attrs.frozen(kw_only=True)
class ExtraResult:
    history: npt.NDArray[np.float64] = attrs.field()
    """Detection history."""

    history_time: npt.NDArray[np.float64] = attrs.field()
    """Time vector for detection history."""

    threshold: float = attrs.field()
    """Threshold."""


@attrs.frozen(kw_only=True)
class ExampleAppResult:
    detection_state: DetectionState = attrs.field()
    """The state of the detection."""

    extra_result: ExtraResult = attrs.field()
    """Extra result used for plotting."""


class ExampleApp(Controller[ExampleAppConfig, ExampleAppResult]):
    """Hand motion detection example app.

    :param client: Client
    :param sensor_id: Sensor id
    :param example_app_config: Hand motion detection configuration
    """

    processor: Processor
    HISTORY_LENGTH_S = 10.0

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        example_app_config: ExampleAppConfig,
    ) -> None:
        super().__init__(client=client, config=example_app_config)
        self.sensor_id = sensor_id
        self.config = example_app_config

        self.detection_retention_duration = int(
            round(example_app_config.detection_retention_duration * example_app_config.frame_rate)
        )

        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, _algo_group: Optional[h5py.Group] = None
    ) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        self._reinitialize_state_variables()

        sensor_config = self._get_sensor_config(self.config)
        self.session_config = a121.SessionConfig(
            {self.sensor_id: sensor_config},
            extended=False,
        )

        metadata = self.client.setup_session(self.session_config)
        assert isinstance(metadata, a121.Metadata)

        self.processor = Processor(
            sensor_config=sensor_config,
            processor_config=self._get_processor_config(self.config),
            context=ProcessorContext(estimated_frame_rate=self.config.frame_rate),
            metadata=metadata,
        )

        if _algo_group is None and isinstance(recorder, a121.H5Recorder):
            _algo_group = recorder.require_algo_group("faucet")

        if _algo_group is not None:
            _record_algo_data(_algo_group, self.sensor_id, self.config)

        if recorder is not None:
            self.client.attach_recorder(recorder)

        self.client.start_session()

        self.started = True

    def _reinitialize_state_variables(self) -> None:
        num_points_history = int(self.HISTORY_LENGTH_S * self.config.frame_rate)
        self.history = np.zeros(num_points_history)
        self.history_time = np.linspace(-self.HISTORY_LENGTH_S, 0, num_points_history)
        self.has_detected = False
        self.update_index = 0

    def get_next(self) -> ExampleAppResult:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        assert self.processor is not None
        processor_result = self.processor.process(result)

        return self._process_processor_result(processor_result, self.config)

    def _process_processor_result(
        self, result: ProcessorResult, config: ExampleAppConfig
    ) -> ExampleAppResult:
        max_presence_score = max(result.inter_presence_score, result.intra_presence_score)

        # Determine detections state.
        detection_state = DetectionState.NO_DETECTION

        if result.presence_detected:
            self.has_detected = True
            self.update_index_at_detection = self.update_index
            detection_state = DetectionState.DETECTION

        if (
            self.has_detected
            and detection_state is not DetectionState.DETECTION
            and (self.update_index - self.update_index_at_detection)
            < self.detection_retention_duration
        ):
            detection_state = DetectionState.RETENTION

        # Prepare extra result(used for plotting).
        self.history = np.roll(self.history, shift=-1, axis=0)
        self.history[-1] = max_presence_score
        extra_result = ExtraResult(
            history=self.history,
            history_time=self.history_time,
            threshold=config.threshold,
        )

        self.update_index += 1

        return ExampleAppResult(detection_state=detection_state, extra_result=extra_result)

    def stop_detector(self) -> Any:
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        self.client.stop_session()
        self.started = False

        return None

    def stop_recorder(self) -> Any:
        recorder = self.client.detach_recorder()
        if recorder is None:
            recorder_result = None
        else:
            recorder_result = recorder.close()

        return recorder_result

    def stop(self) -> Any:
        self.stop_detector()
        recorder_result = self.stop_recorder()

        return recorder_result

    @classmethod
    def _get_sensor_config(cls, config: ExampleAppConfig) -> a121.SensorConfig:
        """Convert example app config parameters to sensor config.

        Creates a subsweep configuration with
        - A subsweep between the sensor and the water jet(if it fits).
        - A subsweep between the water jet and the end of the measurement range(if it fits).
        """
        profile = a121.Profile.PROFILE_1
        step_length = 6
        water_jet_half_width = config.water_jet_width / 2.0

        subsweep_configs = []

        # Determine if subsweep between sensor and water jet is feasible
        if ENVELOPE_FWHM_M[profile] < (config.sensor_to_water_distance - water_jet_half_width):
            subsweep_config = a121.SubsweepConfig()
            subsweep_config.start_point = int(
                round(
                    (
                        config.sensor_to_water_distance
                        - ENVELOPE_FWHM_M[profile]
                        - water_jet_half_width
                    )
                    / APPROX_BASE_STEP_LENGTH_M
                )
            )
            subsweep_config.num_points = 1
            subsweep_config.step_length = step_length
            subsweep_config.profile = profile
            subsweep_config.hwaas = config.hwaas
            subsweep_config.receiver_gain = 4
            subsweep_configs.append(subsweep_config)

        # Determine if subsweep after water jet is required
        if (
            ENVELOPE_FWHM_M[profile] + water_jet_half_width + config.sensor_to_water_distance
            < config.measurement_range_end
        ):
            start_m = (
                config.sensor_to_water_distance + water_jet_half_width + ENVELOPE_FWHM_M[profile]
            )
            start_point = int(round(start_m / APPROX_BASE_STEP_LENGTH_M))
            num_points = max(
                1,
                int(
                    round(
                        (config.measurement_range_end - start_m)
                        / (step_length * APPROX_BASE_STEP_LENGTH_M)
                    )
                ),
            )

            subsweep_config = a121.SubsweepConfig()
            subsweep_config.start_point = start_point
            subsweep_config.num_points = num_points
            subsweep_config.step_length = step_length
            subsweep_config.profile = profile
            subsweep_config.hwaas = config.hwaas
            subsweep_config.receiver_gain = 4
            subsweep_configs.append(subsweep_config)

        sensor_config = a121.SensorConfig(subsweeps=subsweep_configs)
        sensor_config.frame_rate = config.frame_rate
        sensor_config.sweep_rate = config.sweeps_rate
        sensor_config.sweeps_per_frame = config.sweeps_per_frame
        sensor_config.inter_frame_idle_state = a121.IdleState.SLEEP
        sensor_config._inter_sweep_idle_state = a121.IdleState.SLEEP

        return sensor_config

    @classmethod
    def _get_processor_config(cls, config: ExampleAppConfig) -> ProcessorConfig:
        return ProcessorConfig(
            intra_enable=True,
            inter_enable=True,
            intra_detection_threshold=config.threshold,
            inter_detection_threshold=config.threshold,
            inter_frame_presence_timeout=None,
            inter_frame_fast_cutoff=3.0,
            inter_frame_slow_cutoff=0.8,
            inter_frame_deviation_time_const=0.5,
            inter_output_time_const=config.filter_time_const,
            intra_frame_time_const=0.15,
            intra_output_time_const=config.filter_time_const,
        )


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    config: ExampleAppConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )
    app_config_group = algo_group.create_group("example_app_config")
    opser.serialize(config, app_config_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, ExampleAppConfig]:
    sensor_id = int(algo_group["sensor_id"][()])
    config = opser.deserialize(algo_group["example_app_config"], ExampleAppConfig)
    return sensor_id, config
