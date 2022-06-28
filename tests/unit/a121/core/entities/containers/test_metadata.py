import numpy as np
import pytest

from acconeer.exptool import a121


@pytest.fixture
def ref_metadata():
    return a121.Metadata(
        frame_data_length=10,
        sweep_data_length=10,
        subsweep_data_length=np.array([10]),
        subsweep_data_offset=np.array([0]),
        calibration_temperature=10,
        tick_period=50,
        base_step_length_m=0.0025,
        max_sweep_rate=1000.0,
    )


@pytest.fixture
def ref_metadata_dict():
    return {
        "frame_data_length": 10,
        "sweep_data_length": 10,
        "subsweep_data_length": np.array([10]),
        "subsweep_data_offset": np.array([0]),
        "calibration_temperature": 10,
        "tick_period": 50,
        "base_step_length_m": 0.0025,
        "max_sweep_rate": 1000.0,
    }


def test_init(ref_metadata):
    assert ref_metadata.frame_data_length == 10
    assert ref_metadata.sweep_data_length == 10
    assert ref_metadata.subsweep_data_length == np.array([10])
    assert ref_metadata.subsweep_data_offset == np.array([0])
    assert ref_metadata.calibration_temperature == 10
    assert ref_metadata.tick_period == 50
    assert ref_metadata.base_step_length_m == 0.0025
    assert ref_metadata.max_sweep_rate == 1000.0


def test_eq(ref_metadata):
    assert ref_metadata == a121.Metadata(
        frame_data_length=10,
        sweep_data_length=10,
        subsweep_data_length=np.array([10]),
        subsweep_data_offset=np.array([0]),
        calibration_temperature=10,
        tick_period=50,
        base_step_length_m=0.0025,
        max_sweep_rate=1000.0,
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


def test_frame_shape(ref_metadata):
    num_sweeps = 1
    sweep_len = 10
    assert ref_metadata.frame_shape == (num_sweeps, sweep_len)
