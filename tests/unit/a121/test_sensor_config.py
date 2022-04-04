# type: ignore

import pytest

from acconeer.exptool import a121


@pytest.mark.xfail(reason="Not yet implemented")
def test_sweeps_per_frame():
    # Default value

    config = a121.SensorConfig()
    assert config.sweeps_per_frame == 1

    # Conversion

    config.sweeps_per_frame = 2
    assert config.sweeps_per_frame == 2
    assert isinstance(config.sweeps_per_frame, int)

    config.sweeps_per_frame = 3.0
    assert config.sweeps_per_frame == 3
    assert isinstance(config.sweeps_per_frame, int)

    with pytest.raises(ValueError):
        config.sweeps_per_frame = "not-an-int"

    config = a121.SensorConfig(sweeps_per_frame=2)
    assert config.sweeps_per_frame == 2
    assert isinstance(config.sweeps_per_frame, int)

    config = a121.SensorConfig(sweeps_per_frame=3.0)
    assert config.sweeps_per_frame == 3
    assert isinstance(config.sweeps_per_frame, int)

    with pytest.raises(ValueError):
        a121.SensorConfig(sweeps_per_frame="not-an-int")

    # Validation

    config = a121.SensorConfig()

    with pytest.raises(ValueError):
        config.sweeps_per_frame = 0

    assert config.sweeps_per_frame == 1

    with pytest.raises(ValueError):
        a121.SensorConfig(sweeps_per_frame=0)

    # Documentation

    assert a121.SensorConfig.sweeps_per_frame.__doc__
