import pytest

from acconeer.exptool.clients import SocketClient, SPIClient, UARTClient
from acconeer.exptool.utils import autodetect_serial_port
from acconeer.exptool import configs


@pytest.fixture(scope="module")
def setup(request):
    conn_type, *args = request.param

    if conn_type == "spi":
        client = SPIClient()
        sensor = 1
    elif conn_type == "uart":
        port = args[0] or autodetect_serial_port()
        client = UARTClient(port)
        sensor = 1
    elif conn_type == "socket":
        client = SocketClient(args[0])
        sensor = int(args[1])
    else:
        pytest.fail()

    client.connect()
    yield (client, sensor)
    client.disconnect()


def test_envelope(setup):
    client, sensor = setup

    config = configs.EnvelopeServiceConfig(sensor=sensor)
    session_info = client.start_session(config)
    _, sweep = client.get_next()
    client.stop_session()

    assert sweep.shape == (session_info["data_length"], )


def test_setup_twice(setup):
    client, sensor = setup

    config = configs.IQServiceConfig(sensor=sensor)

    config.range_length = 0.2
    info_1 = client.setup_session(config)

    config.range_length = 0.3
    info_2 = client.setup_session(config)

    assert abs(0.2 - info_1["actual_range_length"]) < 0.01
    assert abs(0.3 - info_2["actual_range_length"]) < 0.01
    assert info_1["data_length"] < info_2["data_length"]
