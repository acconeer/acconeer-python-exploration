import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import INT_16_COMPLEX, ResultContext


@pytest.fixture
def good_metadata():
    return a121.Metadata(
        frame_data_length=15,
        sweep_data_length=5,
        subsweep_data_offset=np.array([0, 2]),
        subsweep_data_length=np.array([2, 3]),
        calibration_temperature=0,
        tick_period=0,
        base_step_length_m=0,
        max_sweep_rate=0,
    )


@pytest.fixture
def good_context(good_metadata):
    return ResultContext(
        metadata=good_metadata,
        ticks_per_second=80,
    )


@pytest.fixture
def good_raw_frame():
    return np.array(
        [
            [(0, 0), (1, -1), (2, -2), (3, -3), (4, -4)],
            [(5, -5), (6, -6), (7, -7), (8, -8), (9, -9)],
            [(10, -10), (11, -11), (12, -12), (13, -13), (14, -14)],
        ],
        dtype=INT_16_COMPLEX,
    )


@pytest.fixture
def good_result(good_context, good_raw_frame):
    return a121.Result(
        data_saturated=False,
        frame_delayed=False,
        calibration_needed=False,
        temperature=0,
        tick=120,
        frame=good_raw_frame,
        context=good_context,
    )


def test_frame_complex_conversion(good_result):
    expected_converted_frame = np.array(
        [
            [(0 - 0j), (1 - 1j), (2 - 2j), (3 - 3j), (4 - 4j)],
            [(5 - 5j), (6 - 6j), (7 - 7j), (8 - 8j), (9 - 9j)],
            [(10 - 10j), (11 - 11j), (12 - 12j), (13 - 13j), (14 - 14j)],
        ],
        dtype="complex",
    )

    assert good_result.frame.dtype == expected_converted_frame.dtype
    assert np.array_equal(good_result.frame, expected_converted_frame)


def test_subframes(good_result):
    expected_subframes = [
        np.array(
            [
                [(0 - 0j), (1 - 1j)],
                [(5 - 5j), (6 - 6j)],
                [(10 - 10j), (11 - 11j)],
            ],
            dtype="complex",
        ),
        np.array(
            [
                [(2 - 2j), (3 - 3j), (4 - 4j)],
                [(7 - 7j), (8 - 8j), (9 - 9j)],
                [(12 - 12j), (13 - 13j), (14 - 14j)],
            ],
            dtype="complex",
        ),
    ]

    assert len(good_result.subframes) == 2

    for actual, expected in zip(good_result.subframes, expected_subframes):
        assert actual.dtype == np.dtype("complex")
        assert np.array_equal(actual, expected)


def test_tick_time(good_result):
    assert np.isclose(good_result.tick_time, 1.5)
