# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for the RLG correction grid's interpolation and its
smoothstep blend into a global quadratic fit past the characterized
envelope."""

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool.a2.algo import _rlg_correction as rlg_correction


@pytest.mark.parametrize(
    "az_deg, el_deg",
    [(0.0, 0.0), (10.0, -6.0), (-42.0, 24.0)],
)
def test_matches_measured_grid_deep_inside_the_margin(az_deg, el_deg):
    """More than ``_BLEND_MARGIN_DEG`` inside every edge, the blend weight
    is exactly 0: ``rlg_correction_db`` must reproduce the plain bilinear
    interpolation of the measured grid exactly, with no contribution from
    the quadratic fit."""
    az_grid, el_grid, correction_db = rlg_correction._load_grid()
    assert rlg_correction._blend_weight(np.array(az_deg), np.array(el_deg)) == 0.0

    expected = rlg_correction._bilinear_interp(
        az_grid, el_grid, correction_db, np.array(az_deg), np.array(el_deg)
    )
    result = rlg_correction.rlg_correction_db(az_deg, el_deg)
    assert result == pytest.approx(float(expected))


@pytest.mark.parametrize(
    "az_deg, el_deg",
    [
        (60.0, 40.0),  # exactly at the corner of the envelope
        (-60.0, -40.0),  # exactly at the opposite corner
        (75.0, 0.0),  # past the az edge
        (-75.0, 0.0),  # past the az edge, other side
        (0.0, 55.0),  # past the el edge
        (0.0, -55.0),  # past the el edge, other side
        (90.0, 90.0),  # far corner
        (-90.0, -90.0),  # far corner, other side
    ],
)
def test_matches_quadratic_fit_at_and_beyond_the_envelope_edge(az_deg, el_deg):
    """At and beyond the envelope edge, the blend weight is exactly 1.
    ``rlg_correction_db`` must equal the global quadratic fit exactly, not
    the raw measured grid, which can differ from the fit by a couple of dB
    right at a single corner node."""
    assert rlg_correction._blend_weight(np.array(az_deg), np.array(el_deg)) == 1.0

    expected = rlg_correction._quadratic_correction_db(np.array(az_deg), np.array(el_deg))
    result = rlg_correction.rlg_correction_db(az_deg, el_deg)
    assert result == pytest.approx(float(expected))


def test_blend_weight_ramps_smoothly_across_the_margin():
    _, az_hi = rlg_correction.measured_az_range_deg()

    deep_inside = rlg_correction._blend_weight(np.array(az_hi - 20.0), np.array(0.0))
    margin_start = rlg_correction._blend_weight(
        np.array(az_hi - rlg_correction._BLEND_MARGIN_DEG), np.array(0.0)
    )
    mid_margin = rlg_correction._blend_weight(np.array(az_hi - 5.0), np.array(0.0))
    at_edge = rlg_correction._blend_weight(np.array(az_hi), np.array(0.0))
    past_edge = rlg_correction._blend_weight(np.array(az_hi + 20.0), np.array(0.0))

    assert deep_inside == 0.0
    assert margin_start == 0.0
    assert 0.0 < mid_margin < 1.0
    assert at_edge == 1.0
    assert past_edge == 1.0


def test_blend_transition_has_no_seam():
    """Regression test: sweeping through the margin band and across the
    envelope edge must change smoothly, with no jump where the blend
    starts or where it reaches full weight."""
    _, az_hi = rlg_correction.measured_az_range_deg()
    _, el_hi = rlg_correction.measured_el_range_deg()

    az_deg = az_hi + 10.0  # already past its own edge throughout the sweep
    el_values = np.linspace(el_hi - rlg_correction._BLEND_MARGIN_DEG - 5.0, el_hi + 10.0, 400)
    corrections = np.array([float(rlg_correction.rlg_correction_db(az_deg, e)) for e in el_values])

    step_jumps = np.abs(np.diff(corrections))
    assert step_jumps.max() < 0.1


def test_quadratic_fit_decreases_monotonically_out_to_90_degrees():
    """The quadratic fit decreases away from boresight out to +-90 deg on
    each axis. An upturn in that range would under-provision
    signal_quality_db there."""
    az_line = np.linspace(0.0, 90.0, 181)
    az_values = rlg_correction._quadratic_correction_db(az_line, np.zeros_like(az_line))
    assert np.all(np.diff(az_values) <= 1e-9)

    el_line = np.linspace(0.0, 90.0, 181)
    el_values = rlg_correction._quadratic_correction_db(np.zeros_like(el_line), el_line)
    assert np.all(np.diff(el_values) <= 1e-9)


def test_correction_is_vectorized_consistently_with_scalar():
    az = np.array([75.0, -75.0, 0.0, 60.0])
    el = np.array([0.0, 0.0, 55.0, 40.0])

    vectorized = rlg_correction.rlg_correction_db(az, el)
    scalar = np.array([float(rlg_correction.rlg_correction_db(a, e)) for a, e in zip(az, el)])

    np.testing.assert_allclose(vectorized, scalar)
