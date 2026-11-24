# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs
import numpy as np
import pytest

from acconeer.exptool.a121.algo.hand_motion import _mode_handler
from acconeer.exptool.a121.algo.hand_motion._example_app import ExtraResult
from acconeer.exptool.a121.algo.hand_motion._mode_handler import (
    AppMode,
    DetectionState,
    ExampleAppResult,
    ModeHandler,
    ModeHandlerConfig,
)


@attrs.frozen
class _FakeDetectorResult:
    presence_detected: bool


class _FakeController:
    def __init__(self, **kwargs: t.Any) -> None:
        self.started = False

    def start(self) -> None:
        if self.started:
            msg = "Already started"
            raise RuntimeError(msg)
        self.started = True

    def stop_detector(self) -> None:
        if not self.started:
            msg = "Already stopped"
            raise RuntimeError(msg)
        self.started = False

    def stop(self) -> None:
        self.stop_detector()

    def _assert_started(self) -> None:
        if not self.started:
            msg = "Not started"
            raise RuntimeError(msg)


class _FakeDetector(_FakeController):
    def get_next(self) -> _FakeDetectorResult:
        self._assert_started()
        return _FakeDetectorResult(presence_detected=True)


class _FakeExampleApp(_FakeController):
    def get_next(self) -> ExampleAppResult:
        self._assert_started()
        extra_result = ExtraResult(history=np.zeros(1), history_time=np.zeros(1), threshold=1.5)
        return ExampleAppResult(
            detection_state=DetectionState.NO_DETECTION, extra_result=extra_result
        )


def _mode_handler_with_fakes(
    monkeypatch: pytest.MonkeyPatch, *, use_presence_detection: bool
) -> ModeHandler:
    monkeypatch.setattr(_mode_handler, "Detector", _FakeDetector)
    monkeypatch.setattr(_mode_handler, "DetectorResult", _FakeDetectorResult)
    monkeypatch.setattr(_mode_handler, "ExampleApp", _FakeExampleApp)
    config = ModeHandlerConfig(use_presence_detection=use_presence_detection)
    return ModeHandler(client=t.cast(t.Any, None), sensor_id=1, mode_handler_config=config)


def test_restart_resets_mode_and_timer(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _mode_handler_with_fakes(monkeypatch, use_presence_detection=True)
    handler.start()
    # Presence is detected and the handler swaps to hand motion mode.
    assert handler.get_next().app_mode is AppMode.PRESENCE
    assert handler.get_next().app_mode is AppMode.HANDMOTION
    assert handler.hand_motion_timer == 1
    handler.stop()

    handler.start()
    assert handler.app_mode is AppMode.PRESENCE
    assert handler.hand_motion_timer == 0
    result = handler.get_next()
    assert result.app_mode is AppMode.PRESENCE
    assert result.presence_result == _FakeDetectorResult(presence_detected=True)
    handler.stop()


def test_restart_without_presence_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _mode_handler_with_fakes(monkeypatch, use_presence_detection=False)
    for _ in range(2):
        handler.start()
        result = handler.get_next()
        assert result.app_mode is AppMode.HANDMOTION
        assert result.detection_state is DetectionState.NO_DETECTION
        handler.stop()
