import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance


def test_get_subsweep_configs():
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_1),
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_2),
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_3),
        ],
    )

    actual_subsweeps = distance.DistanceProcessor._get_subsweep_configs(sensor_config, [1, 0])
    actual = [c.profile for c in actual_subsweeps]
    expected = [a121.Profile.PROFILE_2, a121.Profile.PROFILE_1]
    assert actual == expected


def test_get_profile():
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_2),
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_2),
            a121.SubsweepConfig(profile=a121.Profile.PROFILE_3),
        ],
    )

    actual = distance.DistanceProcessor._get_profile(sensor_config, [0, 1])
    assert actual == a121.Profile.PROFILE_2

    with pytest.raises(Exception):
        distance.DistanceProcessor._get_profile(sensor_config, [0, 1, 2])


def test_get_start_point():
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(start_point=100),
            a121.SubsweepConfig(start_point=150),
            a121.SubsweepConfig(start_point=123),
        ],
    )

    actual = distance.DistanceProcessor._get_start_point(sensor_config, [1, 0])
    assert actual == 150


def test_get_num_points():
    sensor_config = a121.SensorConfig(
        subsweeps=[
            a121.SubsweepConfig(num_points=100),
            a121.SubsweepConfig(num_points=150),
            a121.SubsweepConfig(num_points=123),
        ],
    )

    actual = distance.DistanceProcessor._get_num_points(sensor_config, [0, 1])
    assert actual == 250


def test_validate_range():
    distance.DistanceProcessor._validate_range(
        a121.SensorConfig(
            subsweeps=[
                a121.SubsweepConfig(
                    start_point=100,
                    num_points=3,
                    step_length=2,
                ),
                a121.SubsweepConfig(
                    start_point=106,
                    num_points=4,
                    step_length=2,
                ),
            ],
        ),
        [0, 1],
    )

    with pytest.raises(Exception):
        distance.DistanceProcessor._validate_range(
            a121.SensorConfig(
                subsweeps=[
                    a121.SubsweepConfig(
                        start_point=100,
                        num_points=3,
                        step_length=2,
                    ),
                    a121.SubsweepConfig(
                        start_point=100,
                        num_points=4,
                        step_length=2,
                    ),
                ],
            ),
            [0, 1],
        )


def test_get_distance_filter_coeffs():
    (actual_B, actual_A) = distance.DistanceProcessor._get_distance_filter_coeffs(
        a121.Profile.PROFILE_1, 1
    )

    assert actual_B[0] == pytest.approx(0.00844269, 0.01)
    assert actual_B[1] == pytest.approx(0.01688539, 0.01)
    assert actual_B[2] == pytest.approx(0.00844269, 0.01)

    assert actual_A[0] == pytest.approx(1.0, 0.01)
    assert actual_A[1] == pytest.approx(-1.72377617, 0.01)
    assert actual_A[2] == pytest.approx(0.75754694, 0.01)

    (actual_B, actual_A) = distance.DistanceProcessor._get_distance_filter_coeffs(
        a121.Profile.PROFILE_5, 6
    )
    assert actual_B[0] == pytest.approx(0.00490303, 0.01)
    assert actual_B[1] == pytest.approx(0.00980607, 0.01)
    assert actual_B[2] == pytest.approx(0.00490303, 0.01)

    assert actual_A[0] == pytest.approx(1.0, 0.01)
    assert actual_A[1] == pytest.approx(-1.79238564, 0.01)
    assert actual_A[2] == pytest.approx(0.81199778, 0.01)
