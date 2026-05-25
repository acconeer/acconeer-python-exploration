# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    distance,
    find_peaks,
    get_distance_filter_coeffs,
    get_distance_filter_edge_margin,
    interpolate_peaks,
)


def test_apply_phase_jitter_compensation() -> None:
    frame = np.array([0 + 0, 1 + 1j, 2 + 2j, 3 + 3j])
    lb_angle = np.array([np.pi / 2])

    actual_adjuster_frame = distance.CloseRangeProcessor.apply_phase_jitter_compensation(
        frame=frame,
        lb_angle=lb_angle,
        direct_leakage=frame,
        phase_jitter_comp_ref=np.array([0.0]),
    )
    assert actual_adjuster_frame[0] == 0.0 + 0.0j
    assert actual_adjuster_frame[1] == 2.0 + 0.0j
    assert actual_adjuster_frame[2] == 4.0 + 0.0j
    assert actual_adjuster_frame[3] == 6.0 + 0.0j


def test_get_distance_filter_coeffs() -> None:
    (actual_B, actual_A) = get_distance_filter_coeffs(a121.Profile.PROFILE_1, 1)

    assert actual_B[0] == pytest.approx(0.08966060, 0.01)
    assert actual_B[1] == pytest.approx(0.08966060, 0.01)

    assert actual_A[0] == pytest.approx(1.0, 0.01)
    assert actual_A[1] == pytest.approx(-0.82067879, 0.01)

    (actual_B, actual_A) = get_distance_filter_coeffs(a121.Profile.PROFILE_5, 6)
    assert actual_B[0] == pytest.approx(0.06869703, 0.01)
    assert actual_B[1] == pytest.approx(0.06869703, 0.01)

    assert actual_A[0] == pytest.approx(1.0, 0.01)
    assert actual_A[1] == pytest.approx(-0.86260593, 0.01)


def test_find_peaks() -> None:
    abs_sweep = np.array([1, 2, 3, 2, 1, 1, 1, 1, 1, 2, 3, 2, 1, 1, 1])
    threshold_values = np.ones_like(abs_sweep)
    actual_found_peaks = find_peaks(abs_sweep=abs_sweep, threshold_values=threshold_values)

    assert actual_found_peaks[0] == 2
    assert actual_found_peaks[1] == 10


def test_interpolate_peaks() -> None:
    abs_sweep = np.array([1, 2, 3, 2, 1])
    peak_idxs = [2]
    start_point = 0
    step_length = 1
    step_length_m = 0.0025

    (actual_est_dists, actual_est_ampls) = interpolate_peaks(
        abs_sweep=abs_sweep,
        peak_idxs=peak_idxs,
        start_point=start_point,
        step_length=step_length,
        step_length_m=step_length_m,
    )

    assert actual_est_dists[0] == pytest.approx(0.005, 0.0001)
    assert actual_est_ampls[0] == pytest.approx(3, 0.0001)

    abs_sweep = np.array([1, 3, 3, 1])
    peak_idxs = [1]
    start_point = 0
    step_length = 1
    step_length_m = 0.0025

    (actual_est_dists, actual_est_ampls) = interpolate_peaks(
        abs_sweep=abs_sweep,
        peak_idxs=peak_idxs,
        start_point=start_point,
        step_length=step_length,
        step_length_m=step_length_m,
    )

    assert actual_est_dists[0] == pytest.approx(0.00375, 0.0001)
    assert actual_est_ampls[0] == pytest.approx(3.25, 0.01)


def test_distance_filter_edge_margin() -> None:
    profile = a121.Profile.PROFILE_3
    step_length = 4

    actual_filter_edge_margin = get_distance_filter_edge_margin(
        profile=profile, step_length=step_length
    )

    assert actual_filter_edge_margin == 14
