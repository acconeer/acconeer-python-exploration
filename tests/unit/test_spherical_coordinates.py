# Copyright (c) Acconeer AB, 2026
# All rights reserved

import numpy as np
import pytest

from acconeer.exptool.utils import (
    cartesian_to_spherical,
    spherical_to_cartesian,
    spherical_to_cartesian_jacobian,
)


@pytest.mark.parametrize(
    ("x", "y", "z", "expected"),
    [
        (0.0, 2.0, 0.0, (2.0, 0.0, 0.0)),  # boresight on +y
        (1.0, 1.0, 0.0, (np.sqrt(2.0), np.pi / 4, 0.0)),  # +az toward +x
        (0.0, 1.0, 1.0, (np.sqrt(2.0), 0.0, np.pi / 4)),  # +el toward +z
    ],
)
def test_cartesian_to_spherical_convention(x, y, z, expected):
    np.testing.assert_allclose(cartesian_to_spherical(x, y, z), expected, atol=1e-12)


def test_spherical_round_trip():
    rng = np.random.default_rng(0)
    length = rng.uniform(0.1, 10.0, 500)
    # Stay in front of the sensor (y > 0), where the inverse is single-valued.
    az = rng.uniform(-0.49 * np.pi, 0.49 * np.pi, 500)
    el = rng.uniform(-0.49 * np.pi, 0.49 * np.pi, 500)

    round_trip = cartesian_to_spherical(*spherical_to_cartesian(length, az, el))

    np.testing.assert_allclose(round_trip, (length, az, el), rtol=1e-12, atol=1e-12)


def test_cartesian_round_trip():
    rng = np.random.default_rng(1)
    x = rng.uniform(-5.0, 5.0, 500)
    y = rng.uniform(0.1, 5.0, 500)
    z = rng.uniform(-5.0, 5.0, 500)

    round_trip = spherical_to_cartesian(*cartesian_to_spherical(x, y, z))

    np.testing.assert_allclose(round_trip, (x, y, z), rtol=1e-12, atol=1e-12)


def test_cartesian_to_spherical_scalar_input_returns_scalars():
    length, az, el = cartesian_to_spherical(1.0, 1.0, 0.0)

    assert all(np.ndim(v) == 0 for v in (length, az, el))


def test_spherical_to_cartesian_jacobian_matches_finite_differences():
    rng = np.random.default_rng(2)
    eps = 1e-6
    for _ in range(50):
        point = np.array([rng.uniform(-5.0, 5.0), rng.uniform(0.1, 5.0), rng.uniform(-5.0, 5.0)])
        spherical = np.array(cartesian_to_spherical(*point))
        numeric = np.empty((3, 3))
        for col in range(3):
            step = np.zeros(3)
            step[col] = eps
            numeric[:, col] = (
                np.array(spherical_to_cartesian(*(spherical + step)))
                - np.array(spherical_to_cartesian(*(spherical - step)))
            ) / (2 * eps)

        np.testing.assert_allclose(
            spherical_to_cartesian_jacobian(*point), numeric, rtol=1e-6, atol=1e-8
        )


def test_spherical_to_cartesian_jacobian_raises_on_x_axis():
    with pytest.raises(ValueError, match="x-axis"):
        spherical_to_cartesian_jacobian(1.0, 0.0, 0.0)
