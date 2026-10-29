# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Regression tests pinning the subsweep layout WallMountSessionAbstractionConfig
derives for a handful of representative wall mounts and one corner mount.

The wall-mount cases are taken from a sweep over four mounts:

* A0 / A180: level sensor 1.8 m up, evaluation plane at sensor height,
  upright / upside down.
* B0 / B180: sensor 2.0 m up, tilted 20 degrees down, evaluation plane 0.8 m
  below it, upright / upside down.

A failing layout test prints the actual layout. If the change is intended,
paste it into ``EXPECTED_LAYOUTS``.
"""

from __future__ import annotations

import typing as t

import numpy as np
import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._detection_geometry import DetectionVolume, SensorInstallation
from acconeer.exptool.a2.algo._shared_config import WallMountSessionAbstractionConfig
from acconeer.exptool.a2.algo._utils import get_distances


_LEVEL = dict(mount_height_m=1.8)
_TILTED = dict(mount_height_m=2.0, x_rotation=-20.0)

# name -> (SensorInstallation and DetectionVolume kwargs, signal_quality_db,
#          world z of the SNR evaluation plane, frame_rate)
CASES: dict[str, tuple[dict[str, t.Any], float, float, float]] = {
    "a0_narrow_deep_21db": (
        dict(x_bounds_m=(-2.0, 2.0), y_bounds_m=(0.0, 8.0), y_rotation=0.0, **_LEVEL),
        21.0,
        0.0,
        15.0,
    ),
    # The default az range needs a lower signal quality for this volume
    "a180_wide_short_26db_az60": (
        dict(
            x_bounds_m=(-4.0, 4.0),
            y_bounds_m=(0.0, 4.0),
            az_angle_range=(-60.0, 60.0),
            y_rotation=180.0,
            **_LEVEL,
        ),
        26.0,
        0.0,
        15.0,
    ),
    "a180_wide_short_22db": (
        dict(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 4.0), y_rotation=180.0, **_LEVEL),
        22.0,
        0.0,
        15.0,
    ),
    "b0_wide_26db": (
        dict(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 6.0), y_rotation=0.0, **_TILTED),
        26.0,
        -0.8,
        4.0,  # this layout's maximum frame rate is about 5.0 Hz
    ),
    "b180_narrow_26db": (
        dict(x_bounds_m=(-2.0, 2.0), y_bounds_m=(0.0, 6.0), y_rotation=180.0, **_TILTED),
        26.0,
        -0.8,
        15.0,
    ),
    # Mounted in the room's corner at the origin, tilted 20 degrees down and
    # panned -45 degrees so the boresight runs along the room's diagonal.
    "corner_4x4_26db": (
        dict(x_bounds_m=(0.0, 4.0), y_bounds_m=(0.0, 4.0), z_rotation=-45.0, **_TILTED),
        26.0,
        -0.8,
        15.0,
    ),
}

# name -> per subsweep:
# (start_point, num_points, step_length, hwaas_exponent, hwaas_min, hwaas_max, prf)
EXPECTED_LAYOUTS: dict[str, list[tuple[int, int, int, int, int, int, str]]] = {
    "a0_narrow_deep_21db": [
        (344, 11, 129, 0, 1, 3, "PRF_20_8_MHZ"),
        (1763, 7, 129, 3, 1, 13, "PRF_15_8_MHZ"),
        (2666, 4, 129, 3, 1, 27, "PRF_12_5_MHZ"),
        (3182, 2, 129, 0, 1, 32, "PRF_12_5_MHZ"),
    ],
    "a180_wide_short_26db_az60": [
        (375, 6, 129, 4, 1, 7, "PRF_20_8_MHZ"),
        (1149, 5, 129, 4, 1, 47, "PRF_20_8_MHZ"),
        (1794, 2, 129, 0, 1, 61, "PRF_15_8_MHZ"),
        (2052, 3, 129, 1, 1, 66, "PRF_15_8_MHZ"),
    ],
    "a180_wide_short_22db": [
        (375, 5, 129, 3, 1, 7, "PRF_20_8_MHZ"),
        (1020, 5, 129, 4, 1, 58, "PRF_20_8_MHZ"),
        (1665, 1, 129, 0, 1, 48, "PRF_20_8_MHZ"),
        (1794, 5, 129, 0, 1, 29, "PRF_15_8_MHZ"),
    ],
    "b0_wide_26db": [
        (348, 11, 129, 4, 1, 151, "PRF_20_8_MHZ"),
        (1767, 3, 129, 0, 1, 72, "PRF_15_8_MHZ"),
        (2154, 4, 129, 3, 1, 157, "PRF_15_8_MHZ"),
        (2670, 3, 129, 0, 1, 165, "PRF_12_5_MHZ"),
    ],
    "b180_narrow_26db": [
        (395, 5, 129, 4, 1, 13, "PRF_20_8_MHZ"),
        (1040, 5, 129, 1, 1, 8, "PRF_20_8_MHZ"),
        (1685, 7, 129, 3, 1, 29, "PRF_15_8_MHZ"),
        (2588, 1, 129, 0, 1, 28, "PRF_15_8_MHZ"),
    ],
    "corner_4x4_26db": [
        (400, 5, 129, 1, 1, 3, "PRF_20_8_MHZ"),
        (1045, 5, 129, 3, 1, 14, "PRF_20_8_MHZ"),
        (1690, 3, 129, 0, 1, 11, "PRF_15_8_MHZ"),
        (2077, 3, 129, 0, 1, 14, "PRF_15_8_MHZ"),
    ],
}


_INSTALLATION_KEYS = ("x_rotation", "y_rotation", "z_rotation", "mount_height_m")


def _configs(
    name: str,
) -> tuple[WallMountSessionAbstractionConfig, SensorInstallation, DetectionVolume]:
    kwargs, signal_quality_db, snr_evaluation_z_m, frame_rate = CASES[name]
    installation = SensorInstallation(
        **{key: value for key, value in kwargs.items() if key in _INSTALLATION_KEYS}
    )
    volume = DetectionVolume(
        **{key: value for key, value in kwargs.items() if key not in _INSTALLATION_KEYS}
    )
    config = WallMountSessionAbstractionConfig(
        signal_quality_db=signal_quality_db,
        profile=a2.Profile.PROFILE_7,
        frame_rate=frame_rate,
        max_snr_drop_db=2.5,
        sweeps_per_frame=15,
        sweep_rate=None,
        snr_evaluation_height_m=snr_evaluation_z_m + installation.mount_height_m,
    )
    return config, installation, volume


def _layout(
    subsweeps: list[a2.SubsweepConfig],
) -> list[tuple[int, int, int, int, int, int, str]]:
    return [
        (
            s.start_point,
            s.num_points,
            s.step_length,
            s.hwaas_exponent,
            s.hwaas_min,
            s.hwaas_max,
            s.prf.name,
        )
        for s in subsweeps
    ]


def test_every_case_has_an_expected_layout() -> None:
    assert set(CASES) == set(EXPECTED_LAYOUTS)


@pytest.mark.parametrize("name", list(CASES))
def test_layout_matches_regression(name: str) -> None:
    config, installation, volume = _configs(name)
    subsweeps = config.get_session_config(installation, volume).sensor_config.subsweeps

    actual = _layout(subsweeps)
    assert actual == EXPECTED_LAYOUTS[name], f"{name} layout changed, now:\n{actual!r}"
    assert all(s.profile is a2.Profile.PROFILE_7 for s in subsweeps)


@pytest.mark.parametrize("name", list(CASES))
def test_regression_case_validates_cleanly(name: str) -> None:
    config, installation, volume = _configs(name)

    assert config._collect_validation_results(installation, volume) == []


@pytest.mark.parametrize("name", list(CASES))
def test_regression_case_session_config_validates(name: str) -> None:
    config, installation, volume = _configs(name)

    config.get_session_config(installation, volume).validate()


@pytest.mark.parametrize("name", list(CASES))
def test_regression_case_covers_required_hwaas(name: str) -> None:
    """Every point gets at least the HWAAS its worst-case angle needs, after
    hardware quantization."""
    config, installation, volume = _configs(name)
    subsweeps = config.get_session_config(installation, volume).sensor_config.subsweeps
    start_point, num_points = config._get_point_grid_bounds(installation, volume)
    distances_m = get_distances(start_point, config._get_max_step_length(), num_points)
    required = config._required_hwaas_curve(installation, volume, distances_m)

    delivered = np.concatenate([s.hwaas_points for s in subsweeps])

    assert len(delivered) == len(distances_m)
    assert np.all(delivered >= required)


def test_corner_mount_points_into_the_room() -> None:
    """The corner case's rotation aims the boresight along the room diagonal
    (+x, +y) and downward, so the whole floor area lies in front of the sensor."""
    _, installation, _ = _configs("corner_4x4_26db")
    boresight = installation.sensor_to_world([0.0, 1.0, 0.0])

    np.testing.assert_allclose(boresight[0], boresight[1])
    assert boresight[0] > 0.0
    assert boresight[2] < 0.0
