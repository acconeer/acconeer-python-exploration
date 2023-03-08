# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import packaging.version
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core.entities import SensorInfo


@pytest.fixture
def reference_sensor_info() -> SensorInfo:
    return SensorInfo(connected=True)


@pytest.fixture
def reference_dict(reference_sensor_info: SensorInfo) -> dict[str, t.Any]:
    return {
        "rss_version": "a121-v2.3.4",
        "sensor_count": 1,
        "ticks_per_second": 100,
        "sensor_infos": {1: reference_sensor_info.to_dict()},
        "hardware_name": "xy123",
        "max_baudrate": None,
    }


@pytest.fixture
def reference_obj(
    reference_dict: dict[str, t.Any], reference_sensor_info: SensorInfo
) -> a121.ServerInfo:
    return a121.ServerInfo(
        rss_version=reference_dict["rss_version"],
        sensor_count=reference_dict["sensor_count"],
        ticks_per_second=reference_dict["ticks_per_second"],
        sensor_infos={1: reference_sensor_info},
        hardware_name=reference_dict["hardware_name"],
        max_baudrate=None,
    )


def test_to_dict(reference_obj: a121.ServerInfo, reference_dict: dict[str, t.Any]) -> None:
    assert reference_obj.to_dict() == reference_dict


def test_from_dict(reference_obj: a121.ServerInfo, reference_dict: dict[str, t.Any]) -> None:
    assert a121.ServerInfo.from_dict(reference_dict) == reference_obj


def test_from_to_json(reference_obj: a121.ServerInfo) -> None:
    json_str = reference_obj.to_json()
    recreated_obj = a121.ServerInfo.from_json(json_str)
    assert recreated_obj == reference_obj


def test_parsed_rss_version(reference_obj: a121.ServerInfo) -> None:
    assert reference_obj.parsed_rss_version == packaging.version.Version("2.3.4")


def test_sensor_info_str(reference_sensor_info: dict[str, t.Any]) -> None:
    assert str(reference_sensor_info).splitlines() == [
        "SensorInfo:",
        "  connected .............. True",
        "  serial ................. None",
    ]


def test_server_info_str(reference_obj: a121.ServerInfo) -> None:
    assert str(reference_obj).splitlines() == [
        "ServerInfo:",
        "  rss_version ............ a121-v2.3.4",
        "  sensor_count ........... 1",
        "  ticks_per_second ....... 100",
        "  hardware_name .......... xy123",
        "  max_baudrate ........... None",
        "  sensor_infos:",
        "    SensorInfo @ slot 1:",
        "      connected .............. True",
        "      serial ................. None",
    ]
