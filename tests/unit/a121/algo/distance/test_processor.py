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
