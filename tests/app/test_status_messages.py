# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool.app.new.backend._application_client import (
    _CALIBRATION_NEEDED_MESSAGE,
    _DATA_SATURATED_MESSAGE,
    _FRAME_DELAYED_MESSAGE,
    _A2Extractor,
)


def _a2_result(
    *, data_saturated: bool = False, frame_delayed: bool = False, calibration_needed: bool = False
) -> a2.Result:
    return a2.Result(
        frame=np.zeros((1, 4), dtype=np.complex128),
        temperature=21,
        tick=0,
        data_saturated=[data_saturated],
        measured_sweep_rate=7.35,
        frame_delayed=frame_delayed,
        calibration_temperature=25,
        calibration_needed=calibration_needed,
    )


@pytest.mark.parametrize(
    ("flag", "message"),
    [
        ("data_saturated", _DATA_SATURATED_MESSAGE),
        ("frame_delayed", _FRAME_DELAYED_MESSAGE),
        ("calibration_needed", _CALIBRATION_NEEDED_MESSAGE),
    ],
)
def test_an_a2_result_reports_its_status(flag: str, message: str) -> None:
    result = _a2_result(**{flag: True})

    assert _A2Extractor.get_status_messages(result) == [message]
    assert _A2Extractor.get_status_messages(a2.GroupResult(results=[_a2_result(), result])) == [
        message
    ]


def test_a_fine_a2_result_reports_nothing() -> None:
    assert _A2Extractor.get_status_messages(_a2_result()) == []
