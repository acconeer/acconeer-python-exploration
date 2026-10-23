# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for ConcatenatedSubsweepView."""

from __future__ import annotations

import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import ConcatenatedSubsweepView, get_distances_from_config


def _subsweep(
    *,
    start_point: int = 100,
    num_points: int = 40,
    step_length: int = 16,
    profile: a2.Profile = a2.Profile.PROFILE_3,
    tx_antenna_mask: int = 0b111,
    rx_antenna_mask: int = 0b1111,
) -> a2.SubsweepConfig:
    return a2.SubsweepConfig(
        start_point=start_point,
        num_points=num_points,
        step_length=step_length,
        profile=profile,
        tx_antenna_mask=tx_antenna_mask,
        rx_antenna_mask=rx_antenna_mask,
    )


def _contiguous(*subsweeps: a2.SubsweepConfig) -> None:
    """Sanity check for the fixtures used below: assert the given subsweeps are
    already laid out contiguously, so a failing test is caught by the view and
    not by a bug in the fixture itself."""
    prev = subsweeps[0]
    for subsweep in subsweeps[1:]:
        assert subsweep.start_point == prev.start_point + prev.num_points * prev.step_length
        prev = subsweep


def test_single_subsweep_succeeds():
    ss = _subsweep(start_point=100, num_points=40, step_length=16)
    view = ConcatenatedSubsweepView.from_subsweeps([ss])
    assert view.num_points == 40
    assert view.start_point == 100
    assert view.step_length == 16
    assert view.profile == a2.Profile.PROFILE_3
    assert view.tx_antenna_mask == 0b111
    assert view.rx_antenna_mask == 0b1111
    assert view.num_channels == ss.num_channels


def test_two_contiguous_subsweeps_succeeds():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16)
    ss2 = _subsweep(start_point=100 + 40 * 16, num_points=10, step_length=16)
    _contiguous(ss1, ss2)
    view = ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])
    assert view.num_points == 50
    assert view.start_point == 100


def test_n_contiguous_subsweeps_succeeds():
    subsweeps = []
    start_point = 0
    for num_points in (10, 5, 3, 2, 1):
        ss = _subsweep(start_point=start_point, num_points=num_points, step_length=8)
        subsweeps.append(ss)
        start_point += num_points * 8
    _contiguous(*subsweeps)
    view = ConcatenatedSubsweepView.from_subsweeps(subsweeps)
    assert view.num_points == sum(ss.num_points for ss in subsweeps)


def test_empty_input_raises():
    with pytest.raises(ValueError, match="must not be empty"):
        ConcatenatedSubsweepView.from_subsweeps([])


def test_mismatched_profile_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16, profile=a2.Profile.PROFILE_3)
    ss2 = _subsweep(
        start_point=100 + 40 * 16, num_points=10, step_length=16, profile=a2.Profile.PROFILE_5
    )
    _contiguous(ss1, ss2)
    with pytest.raises(ValueError, match="profile"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_mismatched_step_length_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16)
    ss2 = _subsweep(start_point=100 + 40 * 16, num_points=10, step_length=8)
    with pytest.raises(ValueError, match="step_length"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_mismatched_tx_antenna_mask_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16, tx_antenna_mask=0b111)
    ss2 = _subsweep(
        start_point=100 + 40 * 16, num_points=10, step_length=16, tx_antenna_mask=0b011
    )
    _contiguous(ss1, ss2)
    with pytest.raises(ValueError, match="tx_antenna_mask"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_mismatched_rx_antenna_mask_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16, rx_antenna_mask=0b1111)
    ss2 = _subsweep(
        start_point=100 + 40 * 16, num_points=10, step_length=16, rx_antenna_mask=0b0111
    )
    _contiguous(ss1, ss2)
    with pytest.raises(ValueError, match="rx_antenna_mask"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_gap_between_subsweeps_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16)
    ss2 = _subsweep(start_point=100 + 40 * 16 + 1, num_points=10, step_length=16)
    with pytest.raises(ValueError, match="contiguous"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_overlap_between_subsweeps_raises():
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16)
    ss2 = _subsweep(start_point=100 + 40 * 16 - 1, num_points=10, step_length=16)
    with pytest.raises(ValueError, match="contiguous"):
        ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])


def test_duplicate_subsweep_object_is_non_contiguous_and_raises():
    """Passing the same SubsweepConfig object twice is not a valid contiguous
    layout (both instances start at the same point)."""
    ss = _subsweep(start_point=100, num_points=40, step_length=16)
    with pytest.raises(ValueError, match="contiguous"):
        ConcatenatedSubsweepView.from_subsweeps([ss, ss])


def test_mutating_original_subsweep_after_construction_does_not_affect_view():
    """The view snapshots its inputs, so mutating the SubsweepConfig objects the
    caller passed in must not retroactively invalidate the view's invariants."""
    ss1 = _subsweep(start_point=100, num_points=40, step_length=16)
    ss2 = _subsweep(start_point=100 + 40 * 16, num_points=10, step_length=16)
    _contiguous(ss1, ss2)
    view = ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])

    ss1.step_length = 8  # would break uniformity and contiguity if the view aliased ss1

    assert view.step_length == 16
    assert view.num_points == 50
    assert view.start_point == 100


def test_get_distances_from_config_works_on_the_view():
    ss1 = _subsweep(start_point=0, num_points=5, step_length=4)
    ss2 = _subsweep(start_point=20, num_points=3, step_length=4)
    _contiguous(ss1, ss2)
    view = ConcatenatedSubsweepView.from_subsweeps([ss1, ss2])
    distances = get_distances_from_config(view)
    assert len(distances) == 8
