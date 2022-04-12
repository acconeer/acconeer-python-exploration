import json

import pytest

from acconeer.exptool import a121


@pytest.fixture
def reference_dict():
    return {
        "rss_version": "2.3.4",
        "sensor_count": 3,
        "ticks_per_second": 100,
    }


@pytest.fixture
def reference_obj(reference_dict):
    return a121.ServerInfo(**reference_dict)


def test_to_dict(reference_obj, reference_dict):
    assert reference_obj.to_dict() == reference_dict


def test_from_dict(reference_obj, reference_dict):
    assert a121.ServerInfo.from_dict(reference_dict) == reference_obj


def test_from_to_json(reference_obj, reference_dict):
    json_str = reference_obj.to_json()
    recreated_obj = a121.ServerInfo.from_json(json_str)
    assert recreated_obj == reference_obj

    assert json.loads(json_str) == reference_dict
