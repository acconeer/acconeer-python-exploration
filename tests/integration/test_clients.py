import time

import numpy as np
import pytest

from acconeer.exptool import clients, configs, modes, utils


@pytest.fixture(scope="module")
def setup(request):
    conn_type, *args = request.param

    if conn_type == "spi":
        client = clients.SPIClient()
        sensor = 1
    elif conn_type == "uart":
        port = args[0] or utils.autodetect_serial_port()
        client = clients.UARTClient(port)
        sensor = 1
    elif conn_type == "socket":
        client = clients.SocketClient(args[0])
        sensor = int(args[1])
    elif conn_type == "mock":
        client = clients.MockClient()
        sensor = 1
    else:
        pytest.fail()

    client.connect()
    yield (client, sensor)
    client.disconnect()


def test_run_a_host_driven_session(setup):
    client, sensor = setup

    config = configs.EnvelopeServiceConfig()
    config.sensor = sensor
    config.repetition_mode = configs.EnvelopeServiceConfig.RepetitionMode.HOST_DRIVEN

    client.start_session(config)
    client.get_next()
    client.stop_session()


def test_run_a_sensor_driven_session(setup):
    client, sensor = setup

    config = configs.EnvelopeServiceConfig()
    config.sensor = sensor
    config.repetition_mode = configs.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN
    config.update_rate = 10

    client.start_session(config)
    client.get_next()
    client.stop_session()


def test_run_illegal_session(setup):
    client, sensor = setup

    if isinstance(client, clients.MockClient):
        return

    config = configs.EnvelopeServiceConfig()
    config.sensor = sensor
    config.repetition_mode = configs.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN
    config.update_rate = 10
    config.range_interval = [0.2, 2.0]  # too long without stitching

    with pytest.raises(clients.base.SessionSetupError):
        client.setup_session(config)

    config.range_interval = [0.2, 0.4]
    client.start_session(config)
    client.get_next()
    client.stop_session()


@pytest.mark.parametrize("mode", modes.Mode)
def test_sanity_check_output(setup, mode):
    client, sensor = setup

    config = configs.MODE_TO_CONFIG_CLASS_MAP[mode]()
    config.sensor = sensor
    config.range_interval = [0.30, 0.60]  # Important with multiple of 0.06m for sparse

    if mode == modes.Mode.SPARSE:
        config.sweeps_per_frame = 10  # Avoid the default value to make sure it bites

    session_info = client.start_session(config)
    data_info, data = client.get_next()
    client.stop_session()

    assert session_info["range_start_m"] == pytest.approx(config.range_start, abs=0.01)
    assert session_info["range_length_m"] == pytest.approx(config.range_length, abs=0.01)
    assert "step_length_m" in session_info

    if mode == modes.Mode.POWER_BINS:
        assert "bin_count" in session_info
    else:
        assert "data_length" in session_info

    if mode == modes.Mode.SPARSE:
        assert "sweep_rate" in session_info
    else:
        assert "stitch_count" in session_info

    assert type(data_info["data_saturated"]) == bool
    assert type(data_info["missed_data"]) == bool

    assert isinstance(data, np.ndarray)

    if mode == modes.Mode.POWER_BINS:
        assert data.dtype == np.float
        size = session_info["bin_count"]
        assert data.shape == (size, )
        assert 1 < size < 10
    elif mode == modes.Mode.ENVELOPE:
        assert data.dtype == np.float
        size = session_info["data_length"]
        assert data.shape == (size, )
        assert size == pytest.approx(config.range_length / 0.06 * 124, abs=10)
    elif mode == modes.Mode.IQ:
        assert data.dtype == np.complex
        size = session_info["data_length"]
        assert data.shape == (size, )
        assert size == pytest.approx(config.range_length / 0.06 * 124, abs=10)
    elif mode == modes.Mode.SPARSE:
        assert data.dtype == np.float
        data_length = session_info["data_length"]
        num_depths = data_length // config.sweeps_per_frame
        assert num_depths * config.sweeps_per_frame == data_length
        assert data.shape == (config.sweeps_per_frame, num_depths)
        assert 1 < config.sweeps_per_frame <= 64
        assert abs(num_depths - int(float(config.range_length / 0.06))) <= 2
    else:
        pytest.fail("test does not cover all modes")


@pytest.mark.parametrize("mode", modes.Mode)
def test_downsampling_factor(setup, mode):
    client, sensor = setup

    if mode == modes.Mode.POWER_BINS:
        return

    config = configs.MODE_TO_CONFIG_CLASS_MAP[mode]()
    config.sensor = sensor
    config.range_interval = [0.30, 0.60]

    size = None

    for df in (1, 2):
        config.downsampling_factor = df

        session_info = client.start_session(config)
        data_info, data = client.get_next()
        client.stop_session()

        step_length = session_info["step_length_m"]

        if mode == modes.Mode.SPARSE:
            expected = df * 0.06
        else:  # Envelope, IQ
            expected = df * 0.48e-3

        assert step_length == pytest.approx(expected, rel=0.1)

        if size is None:  # df == 1
            size = session_info["data_length"]
        else:  # df == 2, size is assuming df == 1
            assert abs(size - 2 * session_info["data_length"]) <= 2


def test_repetition_mode(setup):
    client, sensor = setup

    def measure(config):
        client.start_session(config)
        client.get_next()
        t0 = time.time()

        missed = False
        n = 5

        for _ in range(n):
            info, data = client.get_next()
            if info["missed_data"]:
                missed = True

        t1 = time.time()
        client.stop_session()
        dt = (t1 - t0) / n
        return (dt, missed)

    config = configs.SparseServiceConfig()
    config.sensor = sensor
    config.range_interval = [0.3, 0.36]
    config.sweeps_per_frame = 50
    config.sweep_rate = 1e3

    nominal_f = config.sweep_rate / config.sweeps_per_frame
    nominal_dt = 1.0 / nominal_f

    # on demand / host driven
    config.repetition_mode = configs.SparseServiceConfig.RepetitionMode.HOST_DRIVEN

    # no rate limit
    config.update_rate = None
    dt, missed = measure(config)
    assert not missed
    assert dt == pytest.approx(nominal_dt, rel=0.15)

    # ok rate limit
    config.update_rate = 0.5 / nominal_dt
    dt, missed = measure(config)
    assert not missed
    assert dt == pytest.approx(nominal_dt * 2.0, rel=0.15)

    # too high rate limit
    config.update_rate = 2.0 / nominal_dt
    dt, missed = measure(config)

    if isinstance(client, clients.SocketClient):  # TODO
        assert missed

    assert dt == pytest.approx(nominal_dt, rel=0.15)

    # streaming / sensor driven
    config.repetition_mode = configs.SparseServiceConfig.RepetitionMode.SENSOR_DRIVEN

    # ok rate
    config.update_rate = 0.5 / nominal_dt
    dt, missed = measure(config)
    assert not missed
    assert dt == pytest.approx(nominal_dt * 2.0, rel=0.15)

    # too high rate
    config.update_rate = 2.0 / nominal_dt
    dt, missed = measure(config)
    assert missed
