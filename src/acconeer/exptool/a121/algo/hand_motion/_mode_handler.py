# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import enum
from typing import Any, Optional, Tuple, Union

import attrs
import h5py
from attributes_doc import attributes_doc

from acconeer.exptool import a121, opser
from acconeer.exptool.a121.algo import (
    AlgoConfigBase,
    Controller,
)
from acconeer.exptool.a121.algo.presence import (
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
)

from ._example_app import DetectionState, ExampleApp, ExampleAppConfig, ExampleAppResult


class AppMode(enum.Enum):
    """Indicating the current operating mode of the application."""

    PRESENCE = enum.auto()
    """Detecting presence."""

    HANDMOTION = enum.auto()
    """Detecting hand motion."""


@attributes_doc
@attrs.mutable(kw_only=True)
class ModeHandlerConfig(AlgoConfigBase):
    example_app_config: ExampleAppConfig = attrs.field(factory=ExampleAppConfig)
    """Hand motion detection configuration."""

    presence_config: DetectorConfig = attrs.field(factory=DetectorConfig)
    """Presence detector configuration."""

    hand_detection_timeout: Optional[float] = attrs.field(default=5.0)
    """Duration without detection before returning back to low power mode (s)."""

    use_presence_detection: Optional[bool] = attrs.field(default=True)
    """If true, use presence detector to wake up hand motion detection. """

    def _collect_validation_results(self) -> list[a121.ValidationResult]:
        validation_results: list[a121.ValidationResult] = []

        return validation_results

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModeHandlerConfig:
        presence_dict = d["presence_config"]
        if presence_dict is not None:
            d["presence_config"] = DetectorConfig.from_dict(presence_dict)

        example_app_dict = d["example_app_config"]
        if example_app_dict is not None:
            d["example_app_config"] = ExampleAppConfig.from_dict(example_app_dict)
        return cls(**d)


opser.register_json_presentable(ModeHandlerConfig)


@attrs.frozen(kw_only=True)
class ModeHandlerResult:
    app_mode: AppMode
    """Application mode."""

    detection_state: Optional[DetectionState] = attrs.field(default=None)
    """Detection state."""

    presence_result: Optional[DetectorResult] = attrs.field(default=None)
    """Presence detector result."""

    example_app_result: Optional[ExampleAppResult] = attrs.field(default=None)
    """Hand motion example app result."""


class ModeHandler(Controller[ModeHandlerConfig, ModeHandlerResult]):
    """
    Application handling the switching between the presence detector and the hand motion
    application.

    :param client: Client
    :param sensor_id: Sensor id
    :param mode_handler_config: Mode handler configuration
    """

    def __init__(
        self,
        *,
        client: a121.Client,
        sensor_id: int,
        mode_handler_config: ModeHandlerConfig,
    ) -> None:
        self.client = client
        self.sensor_id = sensor_id
        self.config = mode_handler_config

        self.example_app_config = mode_handler_config.example_app_config
        self.presence_config = mode_handler_config.presence_config

        # As presence detector is used to lower power consumption, it is assumed that the frame
        # rate is low and can be explicitly set here, rather than estimated in the presence
        # application, introducing latency.
        self.presence_detector_context = DetectorContext(
            estimated_frame_rate=mode_handler_config.presence_config.frame_rate
        )

        assert mode_handler_config.hand_detection_timeout is not None
        # Convert timeout from seconds to frames.
        self.hand_motion_timeout_duration = int(
            round(mode_handler_config.hand_detection_timeout * self.example_app_config.frame_rate)
        )
        self.use_presence_detection = mode_handler_config.use_presence_detection

        if self.use_presence_detection:
            self.app_mode = AppMode.PRESENCE
        else:
            self.app_mode = AppMode.HANDMOTION
        self.hand_motion_timer = 0
        self.started = False

    def start(
        self, recorder: Optional[a121.Recorder] = None, _algo_group: Optional[h5py.Group] = None
    ) -> None:
        """Start application."""
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)

        if _algo_group is None and isinstance(recorder, a121.H5Recorder):
            _algo_group = recorder.require_algo_group("hand_motion")

        if recorder is not None:
            self.client.attach_recorder(recorder)

        if _algo_group is not None:
            _record_algo_data(_algo_group, self.sensor_id, self.config)

        if self.use_presence_detection:
            self.presence_detector = Detector(
                client=self.client,
                sensor_id=self.sensor_id,
                detector_config=self.presence_config,
                detector_context=self.presence_detector_context,
            )
            self.presence_detector.start()
        else:
            self.hand_motion_app = ExampleApp(
                client=self.client,
                sensor_id=self.sensor_id,
                example_app_config=self.example_app_config,
            )
            self.hand_motion_app.start()

        self.started = True

    def stop(self) -> Any:
        """Stop application."""
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)

        if self.use_presence_detection and self.presence_detector.started:
            recorder_result = self.presence_detector.stop()
        elif self.hand_motion_app.started:
            recorder_result = self.hand_motion_app.stop()
        else:
            msg = "No active session to stop."
            raise RuntimeError(msg)

        self.started = False

        return recorder_result

    def get_next(self) -> ModeHandlerResult:
        """Get next result."""
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)

        if self.app_mode == AppMode.PRESENCE:
            presence_result = self.presence_detector.get_next()
            result = self._determine_mode_swap(app_result=presence_result)
        elif self.app_mode == AppMode.HANDMOTION:
            hand_motion_result = self.hand_motion_app.get_next()
            result = self._determine_mode_swap(app_result=hand_motion_result)
        else:
            msg = "Invalid app"
            raise RuntimeError(msg)

        return result

    def _determine_mode_swap(
        self, app_result: Union[DetectorResult, ExampleAppResult]
    ) -> ModeHandlerResult:
        """Determine if mode should be swapped, based on result."""
        current_app_mode = self.app_mode

        # Determine if mode should be swapped
        if self.app_mode == AppMode.PRESENCE:
            assert isinstance(app_result, DetectorResult)
            if app_result.presence_detected:
                self.app_mode = AppMode.HANDMOTION
            result = ModeHandlerResult(app_mode=current_app_mode, presence_result=app_result)
        elif self.app_mode == AppMode.HANDMOTION:
            assert isinstance(app_result, ExampleAppResult)
            if self.use_presence_detection:
                if app_result.detection_state is not DetectionState.NO_DETECTION:
                    # detection -> reset timer
                    self.hand_motion_timer = 0
                elif self.hand_motion_timeout_duration < self.hand_motion_timer:
                    # timer has expired -> switch mode
                    self.app_mode = AppMode.PRESENCE
                else:
                    self.hand_motion_timer += 1
            result = ModeHandlerResult(
                app_mode=current_app_mode,
                detection_state=app_result.detection_state,
                example_app_result=app_result,
            )
        else:
            msg = "Invalid app mode"
            raise RuntimeError(msg)

        if self.app_mode != current_app_mode:
            self._swap_mode()

        return result

    def _swap_mode(self) -> None:
        """Swaps mode by stopping current application and create and start a new application."""
        if self.app_mode == AppMode.PRESENCE:
            self.hand_motion_app.stop_detector()
            self.presence_detector = Detector(
                client=self.client,
                sensor_id=self.sensor_id,
                detector_config=self.presence_config,
                detector_context=self.presence_detector_context,
            )
            self.presence_detector.start()
        elif self.app_mode == AppMode.HANDMOTION:
            self.presence_detector.stop_detector()
            self.hand_motion_app = ExampleApp(
                client=self.client,
                sensor_id=self.sensor_id,
                example_app_config=self.example_app_config,
            )
            self.hand_motion_app.start()
            self.hand_motion_timer = 0
        else:
            msg = "Invalid app"
            raise RuntimeError(msg)


def get_default_config() -> ModeHandlerConfig:
    # Create presence config with low power and high responsiveness.
    presence_config = DetectorConfig()
    presence_config.frame_rate = 2
    presence_config.start_m = 0.7
    presence_config.end_m = 0.7
    presence_config.sweeps_per_frame = 32
    presence_config.hwaas = 4
    presence_config.inter_frame_deviation_time_const = 0.01
    presence_config.inter_output_time_const = 0.01
    presence_config.intra_frame_time_const = 0.01
    presence_config.intra_output_time_const = 0.01

    return ModeHandlerConfig(presence_config=presence_config)


def _record_algo_data(
    algo_group: h5py.Group,
    sensor_id: int,
    config: ModeHandlerConfig,
) -> None:
    algo_group.create_dataset(
        "sensor_id",
        data=sensor_id,
        track_times=False,
    )

    handle_config_group = algo_group.create_group("mode_handler_config")
    opser.serialize(config, handle_config_group)


def _load_algo_data(algo_group: h5py.Group) -> Tuple[int, ModeHandlerConfig]:
    sensor_id = int(algo_group["sensor_id"][()])
    config = opser.deserialize(algo_group["mode_handler_config"], ModeHandlerConfig)
    return sensor_id, config
