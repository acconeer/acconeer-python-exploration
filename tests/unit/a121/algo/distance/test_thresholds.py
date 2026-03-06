# Copyright (c) Acconeer AB, 2026
# All rights reserved

import numpy as np
import numpy.testing as npt

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance import _thresholds


def test_cfar_threshold_calc_guard_half_length() -> None:
    profile = a121.Profile.PROFILE_3
    step_length = 4
    actual_guard_half_length = _thresholds.CfarThreshold._calc_guard_half_length(
        profile=profile, step_length=step_length
    )
    assert actual_guard_half_length == 28


def test_cfar_threshold_calc_window_length() -> None:
    profile = a121.Profile.PROFILE_3
    step_length = 2
    actual_window_length = _thresholds.CfarThreshold._calc_window_length(
        profile=profile, step_length=step_length
    )
    assert actual_window_length == 7


def test_cfar_threshold_calculate_threshold_values() -> None:
    # Profile 1, step_length=4 gives window_length=1, guard_half_length=8, margin=9.
    # With window=1 the moving average is the identity, so for a 30-point sweep:
    #   n_valid = 30 - 2*9 = 12
    #   threshold[9 + j] = (abs_sweep[j] + abs_sweep[18 + j]) / 2
    # start_point=100 ensures one-sided mode is off (breakpoint_lim=57 < 100).
    cfar = _thresholds.CfarThreshold(
        sensitivity=0.0,
        bg_noise_std_per_subsweep=[],
        profile=a121.Profile.PROFILE_1,
        start_point=100,
        step_length=4,
        subsweep_slices_cropped=[],
    )

    assert cfar.window_length == 1
    assert cfar.guard_half_length == 8
    assert cfar.margin == 9
    assert cfar.one_sided_breakpoint_in_sweep is None

    abs_sweep = np.ones(30, dtype=np.float64)
    abs_sweep[4:6] = 2.0

    threshold = cfar._calculate_threshold_values(abs_sweep, temperature=0)

    # Margins are undefined (NaN)
    assert np.all(np.isnan(threshold[:9]))
    assert np.all(np.isnan(threshold[-9:]))

    # Valid region: bump at sweep[4:6] lifts positions 13-14 to 1.5; rest stays 1.0
    npt.assert_almost_equal(
        threshold[9:21],
        [1.0, 1.0, 1.0, 1.0, 1.5, 1.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        decimal=4,
    )
