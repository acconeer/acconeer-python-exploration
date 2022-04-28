import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core._entities import SensorDataType


@pytest.fixture
def ref_metadata():
    return a121.Metadata(
        frame_data_length=10,
        sweep_data_length=10,
        subsweep_data_length=np.array([10]),
        subsweep_data_offset=np.array([0]),
        data_type=SensorDataType.INT_16_COMPLEX,
    )


@pytest.fixture
def ref_metadata_dict():
    return {
        "frame_data_length": 10,
        "sweep_data_length": 10,
        "subsweep_data_length": np.array([10]),
        "subsweep_data_offset": np.array([0]),
        "data_type": SensorDataType.INT_16_COMPLEX,
    }


def test_init(ref_metadata):
    assert ref_metadata.frame_data_length == 10
    assert ref_metadata.sweep_data_length == 10
    assert ref_metadata.subsweep_data_length == np.array([10])
    assert ref_metadata.subsweep_data_offset == np.array([0])


def test_eq(ref_metadata):
    assert ref_metadata == a121.Metadata(
        frame_data_length=10,
        sweep_data_length=10,
        subsweep_data_length=np.array([10]),
        subsweep_data_offset=np.array([0]),
        data_type=SensorDataType.INT_16_COMPLEX,
    )


def test_to_dict(ref_metadata, ref_metadata_dict):
    d = ref_metadata.to_dict()
    assert d == ref_metadata_dict
    assert isinstance(d["subsweep_data_length"], np.ndarray)
    assert isinstance(d["subsweep_data_offset"], np.ndarray)


def test_from_dict(ref_metadata, ref_metadata_dict):
    constructed = a121.Metadata.from_dict(ref_metadata_dict)
    assert constructed == ref_metadata
    assert isinstance(constructed.subsweep_data_length, np.ndarray)
    assert isinstance(constructed.subsweep_data_offset, np.ndarray)


def test_to_from_dict_equality(ref_metadata):
    reconstructed = a121.Metadata.from_dict(ref_metadata.to_dict())
    assert reconstructed == ref_metadata
    assert isinstance(reconstructed.subsweep_data_length, np.ndarray)
    assert isinstance(reconstructed.subsweep_data_offset, np.ndarray)


def test_to_from_json_equality(ref_metadata):
    reconstructed = a121.Metadata.from_json(ref_metadata.to_json())
    assert reconstructed == ref_metadata
    assert isinstance(reconstructed.subsweep_data_length, np.ndarray)
    assert isinstance(reconstructed.subsweep_data_offset, np.ndarray)
