# Copyright (c) Acconeer AB, 2022
# All rights reserved

import packaging.version
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import SensorInfo


@pytest.fixture
def reference_sensor_info():
    return SensorInfo(connected=True)


@pytest.fixture
def reference_dict(reference_sensor_info):
    return {
        "rss_version": "a121-v2.3.4",
        "sensor_count": 1,
        "ticks_per_second": 100,
        "sensor_infos": {1: reference_sensor_info.to_dict()},
        "hardware_name": "xy123",
        "max_baudrate": None,
    }


@pytest.fixture
def reference_obj(reference_dict, reference_sensor_info):
    return a121.ServerInfo(
        rss_version=reference_dict["rss_version"],
        sensor_count=reference_dict["sensor_count"],
        ticks_per_second=reference_dict["ticks_per_second"],
        sensor_infos={1: reference_sensor_info},
        hardware_name=reference_dict["hardware_name"],
        max_baudrate=None,
    )


def test_to_dict(reference_obj, reference_dict):
    assert reference_obj.to_dict() == reference_dict


def test_from_dict(reference_obj, reference_dict):
    assert a121.ServerInfo.from_dict(reference_dict) == reference_obj


def test_from_to_json(reference_obj):
    json_str = reference_obj.to_json()
    recreated_obj = a121.ServerInfo.from_json(json_str)
    assert recreated_obj == reference_obj


def test_parsed_rss_version(reference_obj):
    assert reference_obj.parsed_rss_version == packaging.version.Version("2.3.4")
