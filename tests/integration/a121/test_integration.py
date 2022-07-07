import numpy as np
import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils


def test_can_connect():
    with a121.Client(ip_address="localhost") as client:
        assert client.connected


class TestMockExplorationServerDataParsing:
    @pytest.fixture
    def expected_sweep(self):
        return np.array(
            [100 + 100j, 101 + 101j, 102 + 102j, 103 + 103j, 104 + 104j],
        )

    @pytest.mark.parametrize(
        "config",
        [
            a121.SessionConfig(a121.SensorConfig(num_points=5, start_point=100), extended=True),
            a121.SessionConfig(
                [
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                ]
            ),
            a121.SessionConfig(
                [
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                    {1: a121.SensorConfig(num_points=5, start_point=100)},
                ]
            ),
        ],
    )
    def test_sweep(self, config: a121.SessionConfig, expected_sweep):
        assert config.extended
        with a121.Client(ip_address="localhost") as client:
            client.setup_session(config)

            client.start_session()
            result = client.get_next()
            client.stop_session()

            assert isinstance(result, list)
            for _, _, result in utils.iterate_extended_structure(result):
                for sweep in result.frame:
                    np.testing.assert_equal(sweep, expected_sweep)
