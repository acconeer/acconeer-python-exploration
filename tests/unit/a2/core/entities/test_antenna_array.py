# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import random

import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2._core.entities.antenna_array.antenna_array import (
    CHEB_CORR_AP212_R2_PROFILE_3,
    CHEB_CORR_AP212_R2_PROFILE_6,
    AntennaArray,
    Pos,
    _AntennaArrayData,
)


def rand_pos() -> Pos:
    return Pos(random.random(), random.random(), random.random())


def test_can_be_instantiated_by_name() -> None:
    assert AntennaArray("AP212") == AntennaArray.AP212
    assert AntennaArray["AP212"] == AntennaArray.AP212


def test_repr_names_the_member_only() -> None:
    assert repr(AntennaArray.AP212_R2) == "AntennaArray.AP212_R2"


def test_can_be_instantiated_from_data() -> None:
    assert (
        AntennaArray(
            {
                "txs": {0: rand_pos(), 1: rand_pos(), 2: rand_pos()},
                "rxs": {0: rand_pos(), 1: rand_pos(), 2: rand_pos(), 3: rand_pos()},
                "antenna_cheb_corr": [],
            }
        )
        == AntennaArray.AP212
    )


def test_uncorrected_output() -> None:
    expected_output = [
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
        0.28867513 + 0.0j,
    ]
    actual_output = AntennaArray.AP212.get_steering_vector(
        0.0, 0.0, tx_mask=0b111, rx_mask=0b1111, corrected=False, profile=a2.Profile.PROFILE_3
    )

    np.testing.assert_allclose(actual_output, expected_output, rtol=1e-7)


def test_get_correction_scalar_dispatches_to_2d_for_a_3d_table() -> None:
    # A tiny synthetic 2D (az, el) table -- degree 1 in both az and el, 1
    # channel -- constructed directly (not through the AntennaArray enum, so
    # this is independent of AP212_R2's real, much larger fitted table).
    coef = np.array([[[1.0 + 0.5j], [0.25 - 0.1j]], [[0.1j], [0.05 + 0.05j]]])
    array = _AntennaArrayData(txs={}, rxs={}, antenna_cheb_corr=dict.fromkeys(a2.Profile, coef))

    az, el = 0.3, -0.2
    actual = array.get_correction_scalar(
        channel_number=0, az=az, el=el, profile=a2.Profile.PROFILE_1
    )

    expected = np.polynomial.chebyshev.chebval2d(np.sin(az), np.sin(el), coef[:, :, 0])
    np.testing.assert_allclose(actual, expected)


def test_get_correction_scalar_falls_back_to_1d_for_a_2d_table() -> None:
    # Same shape convention as the legacy 1D tables: (az_deg+1, n_channels),
    # i.e. antenna_cheb_corr.ndim == 2 -- must take the chebval (not
    # chebval2d) branch, and el must have no effect on the result.
    coef = np.array([[1.0 + 0.5j], [0.25 - 0.1j]])
    array = _AntennaArrayData(txs={}, rxs={}, antenna_cheb_corr=dict.fromkeys(a2.Profile, coef))

    az = 0.3
    at_el_zero = array.get_correction_scalar(
        channel_number=0, az=az, el=0.0, profile=a2.Profile.PROFILE_1
    )
    at_other_el = array.get_correction_scalar(
        channel_number=0, az=az, el=1.2, profile=a2.Profile.PROFILE_1
    )

    expected = np.polynomial.chebyshev.chebval(np.sin(az), coef)[0]
    np.testing.assert_allclose(at_el_zero, expected)
    np.testing.assert_allclose(at_other_el, expected)


def test_ap212_r2_corrected_steering_vector_depends_on_elevation() -> None:
    # This is the property that was silently broken before AP212_R2 got a
    # fitted 2D correction table: a 1D (az-only) correction can't make the
    # corrected steering vector depend on el at all beyond what the nominal
    # (uncorrected) geometry already contributes on its own.
    az = 0.4
    at_el_zero = AntennaArray.AP212_R2.get_steering_vector(
        az, 0.0, rx_mask=0b1111, tx_mask=0b111, corrected=True, profile=a2.Profile.PROFILE_6
    )
    at_other_el = AntennaArray.AP212_R2.get_steering_vector(
        az, 0.35, rx_mask=0b1111, tx_mask=0b111, corrected=True, profile=a2.Profile.PROFILE_6
    )

    assert not np.allclose(at_el_zero, at_other_el)


@pytest.mark.parametrize("table", [CHEB_CORR_AP212_R2_PROFILE_3, CHEB_CORR_AP212_R2_PROFILE_6])
def test_cheb_corr_ap212_r2_tables_are_sane(table: list[list[list[complex]]]) -> None:
    coef = np.asarray(table)

    assert coef.shape == (10, 6, 12)  # (az_deg+1, el_deg+1, channel)
    assert np.iscomplexobj(coef)
    assert np.all(np.isfinite(coef))


def test_ap212_r2_selects_the_table_by_profile() -> None:
    tables = AntennaArray.AP212_R2.antenna_cheb_corr

    for profile in a2.Profile:
        expected = (
            CHEB_CORR_AP212_R2_PROFILE_3 if profile.value <= 5 else CHEB_CORR_AP212_R2_PROFILE_6
        )
        np.testing.assert_array_equal(tables[profile], np.asarray(expected))


def test_get_correction_scalar_uses_the_table_of_the_profile() -> None:
    coef_3 = np.array([[[1.0 + 0.5j]], [[0.25 - 0.1j]]])
    coef_6 = np.array([[[-0.5 + 1.0j]], [[0.1 + 0.3j]]])
    array = _AntennaArrayData(
        txs={},
        rxs={},
        antenna_cheb_corr={**dict.fromkeys(a2.Profile, coef_3), a2.Profile.PROFILE_6: coef_6},
    )

    az, el = 0.3, -0.2
    for profile, coef in ((a2.Profile.PROFILE_3, coef_3), (a2.Profile.PROFILE_6, coef_6)):
        actual = array.get_correction_scalar(channel_number=0, az=az, el=el, profile=profile)
        expected = np.polynomial.chebyshev.chebval2d(np.sin(az), np.sin(el), coef[:, :, 0])
        np.testing.assert_allclose(actual, expected)


def test_antenna_array_data_needs_a_table_for_every_profile() -> None:
    coef = np.array([[1.0 + 0.5j]])

    with pytest.raises(ValueError, match="PROFILE_2"):
        _AntennaArrayData(txs={}, rxs={}, antenna_cheb_corr={a2.Profile.PROFILE_1: coef})
