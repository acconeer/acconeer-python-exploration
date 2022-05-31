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
