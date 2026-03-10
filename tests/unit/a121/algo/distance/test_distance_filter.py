# Copyright (c) Acconeer AB, 2026
# All rights reserved

import numpy as np
import numpy.testing as npt
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import get_distance_filter_edge_margin
from acconeer.exptool.a121.algo.distance._processors import DistanceFilter


_PROFILE = a121.Profile.PROFILE_3
_STEP_LENGTH = 4
_MARGIN = 14  # get_distance_filter_edge_margin(PROFILE_3, step_length=4)
_NUM_POINTS = 100


def _make_filter(start_point: int = 100) -> DistanceFilter:
    return DistanceFilter(_PROFILE, start_point=start_point, step_length=_STEP_LENGTH)


def _ones_sweep(n: int = _NUM_POINTS) -> np.ndarray:
    return np.ones(n, dtype=np.complex128)


# --- margin ---


def test_margin_property_matches_helper() -> None:
    f = _make_filter()
    assert f.margin == get_distance_filter_edge_margin(_PROFILE, _STEP_LENGTH)


def test_margin_property_matches_known_value() -> None:
    assert _make_filter().margin == _MARGIN


# --- narrow vs wide filter selection ---


def test_narrow_filter_selected_below_breakpoint() -> None:
    # start_point < 40 -> narrow (wider passband) -> higher Butterworth Wn -> larger b[0]
    f_narrow = DistanceFilter(_PROFILE, start_point=0, step_length=_STEP_LENGTH)
    f_wide = DistanceFilter(_PROFILE, start_point=40, step_length=_STEP_LENGTH)
    assert f_narrow._b[0] > f_wide._b[0]


def test_wide_filter_selected_at_breakpoint() -> None:
    # start_point == 40 is not below the breakpoint
    f_at = DistanceFilter(_PROFILE, start_point=40, step_length=_STEP_LENGTH)
    f_above = DistanceFilter(_PROFILE, start_point=100, step_length=_STEP_LENGTH)
    assert f_at._b[0] == pytest.approx(f_above._b[0])


# --- apply: output shape ---


def test_apply_1d_output_length() -> None:
    result = _make_filter().apply(_ones_sweep())
    assert len(result) == _NUM_POINTS - 2 * _MARGIN


def test_apply_2d_frame_output_length() -> None:
    frame = np.stack([_ones_sweep(), _ones_sweep() * 3])
    result = _make_filter().apply(frame)
    assert len(result) == _NUM_POINTS - 2 * _MARGIN


def test_apply_2d_frame_matches_averaged_sweep() -> None:
    # apply(frame) must equal apply(mean of sweeps)
    sweep_a = _ones_sweep()
    sweep_b = _ones_sweep() * 3.0
    frame = np.stack([sweep_a, sweep_b])

    f = _make_filter()
    result_frame = f.apply(frame)
    result_avg = f.apply(np.full(_NUM_POINTS, 2.0 + 0j))

    npt.assert_array_equal(result_frame, result_avg)


def test_apply_raises_on_3d_input() -> None:
    f = _make_filter()
    with pytest.raises(ValueError, match="3D"):
        f.apply(np.ones((2, _NUM_POINTS, 3), dtype=np.complex128))


# --- apply: zero-margin edge case (regression for margin=0 bug) ---


def test_apply_zero_margin_returns_full_array() -> None:
    f = _make_filter()
    f._margin = 0
    sweep = _ones_sweep()
    result = f.apply(sweep)
    assert len(result) == _NUM_POINTS


# --- compute_envelope ---


def test_compute_envelope_dtype_is_float64() -> None:
    result = _make_filter().compute_envelope(_ones_sweep())
    assert result.dtype == np.float64


def test_compute_envelope_is_nonnegative() -> None:
    sweep = np.exp(1j * np.linspace(0, 2 * np.pi, _NUM_POINTS)).astype(np.complex128)
    result = _make_filter().compute_envelope(sweep)
    assert np.all(result >= 0)


def test_compute_envelope_matches_abs_of_apply() -> None:
    f = _make_filter()
    sweep = _ones_sweep() * (1 + 1j)
    npt.assert_array_equal(f.compute_envelope(sweep), np.abs(f.apply(sweep)))
