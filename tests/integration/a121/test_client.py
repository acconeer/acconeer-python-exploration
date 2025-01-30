# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved
from __future__ import annotations

import pytest

from acconeer.exptool import a121
from acconeer.exptool._core.communication import ClientError


@pytest.fixture(params=["es_kwargs", "mock_kwargs"])
def client_kwargs(request, worker_tcp_port: int, a121_exploration_server: None):
    if request.param == "es_kwargs":
        return {"ip_address": "localhost", "tcp_port": worker_tcp_port}
    elif request.param == "mock_kwargs":
        return {"mock": True}
    else:
        pytest.fail(f"Unknown kwargs {request.param!r}")


@pytest.fixture
def tmp_h5_file_path(tmp_path):
    return tmp_path / "record.h5"


@pytest.fixture
def h5_recorder(tmp_h5_file_path):
    with a121.H5Recorder(tmp_h5_file_path) as recorder:
        yield recorder


class CanAttachAndDetachRecorder:
    """Mixin test cases for Client's Recorder handling in all happy paths"""

    def test_can_attach_a_recorder(self, client, h5_recorder):
        client.attach_recorder(h5_recorder)

    def test_can_detach_recorder(self, client, h5_recorder):
        assert client.detach_recorder() is None

        client.attach_recorder(h5_recorder)
        assert client.detach_recorder() is h5_recorder

    def test_can_only_have_one_recorder_attached_at_a_time(self, client, h5_recorder):
        client.attach_recorder(h5_recorder)

        with pytest.raises(ClientError):
            client.attach_recorder(h5_recorder)


class CannotPlayAroundWithRecorder:
    """Mixin test cases for Client's Recorder handling in all sad paths"""

    def test_cannot_attach_a_recorder(self, client, h5_recorder):
        with pytest.raises(ClientError):
            client.attach_recorder(h5_recorder)

    def test_cannot_detach_a_recorder(self, client, h5_recorder):
        with pytest.raises(ClientError):
            client.detach_recorder()


class TestAClosedClient(CannotPlayAroundWithRecorder):
    @pytest.fixture
    def client(self, client_kwargs):
        c = a121.Client.open(**client_kwargs)
        c.close()
        yield c
        if c.connected:
            c.close()

    def test_reports_correct_statuses(self, client):
        assert not client.connected
        assert not client.session_is_setup
        assert not client.session_is_started

    def test_cannot_be_started(self, client):
        with pytest.raises(ClientError):
            client.start_session()

    def test_cannot_get_next_result(self, client):
        with pytest.raises(ClientError):
            _ = client.get_next()

    def test_doesnt_have_server_info(self, client):
        with pytest.raises(ClientError):
            _ = client.server_info

    def test_doesnt_have_session_config(self, client):
        with pytest.raises(ClientError):
            _ = client.session_config

    def test_doesnt_have_any_metadata(self, client):
        with pytest.raises(ClientError):
            _ = client.extended_metadata


class TestAConnectedClient(CanAttachAndDetachRecorder):
    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            yield c

    def test_can_access_server_info(self, client):
        _ = client.server_info

    def test_the_server_info_is_not_none(self, client):
        assert client.server_info is not None

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert not client.session_is_setup
        assert not client.session_is_started

    def test_cannot_start_session(self, client):
        with pytest.raises(ClientError):
            client.start_session()

    def test_cannot_get_next(self, client):
        with pytest.raises(ClientError):
            _ = client.get_next()

    def test_cannot_access_session_config(self, client):
        with pytest.raises(ClientError):
            _ = client.session_config

    def test_cannot_access_metadata(self, client):
        with pytest.raises(ClientError):
            _ = client.extended_metadata


class TestASetupClient(CanAttachAndDetachRecorder):
    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            yield c

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert not client.session_is_started

    def test_can_access_all_data_structures(self, client):
        _ = client.server_info
        _ = client.session_config
        _ = client.extended_metadata

    def test_no_data_structures_are_none(self, client):
        assert client.server_info is not None
        assert client.session_config is not None
        assert client.extended_metadata is not None

    def test_cannot_get_next(self, client):
        with pytest.raises(ClientError):
            _ = client.get_next()

    def test_can_be_setup_again(self, client):
        old_metadata = client.extended_metadata
        client.setup_session(
            a121.SensorConfig(
                sweeps_per_frame=client.session_config.sensor_config.sweeps_per_frame + 1
            )
        )
        assert old_metadata != client.extended_metadata

    def test_calibrations_after_setup(self, client):
        calibrations = client.calibrations
        assert calibrations

        for group in client.session_config.groups:
            for sensor_id in group:
                assert calibrations.get(sensor_id)

    def test_multiple_calibrations_after_setup(self, client):
        client.setup_session(
            a121.SessionConfig(
                [
                    {2: a121.SensorConfig()},
                    {3: a121.SensorConfig()},
                ]
            )
        )

        calibrations = client.calibrations
        assert 1 not in calibrations
        assert 2 in calibrations
        assert 3 in calibrations
        assert 4 not in calibrations

    def test_recording_calibration(self, client, tmp_h5_file_path):
        setup_calibrations = client.calibrations
        assert setup_calibrations

        _ = a121.H5Recorder(tmp_h5_file_path, client)
        client.start_session()
        [client.get_next() for _ in range(5)]
        client.stop_session()

        record = a121.load_record(tmp_h5_file_path)
        for sensor_id in setup_calibrations:
            assert sensor_id in record.calibrations
            assert setup_calibrations[sensor_id].data == record.calibrations[sensor_id].data
            assert (
                setup_calibrations[sensor_id].temperature
                == record.calibrations[sensor_id].temperature
            )
            assert not record.calibrations_provided[sensor_id]

    def test_not_calibrations_provided(self, client):
        calibrations_provided = client.calibrations_provided

        for _, provided in calibrations_provided.items():
            assert not provided

    def test_multiple_calibrations_provided_after_setup(self, client):
        calibrations = client.calibrations
        assert calibrations

        calibration = calibrations.get(1)
        assert calibration

        client.setup_session(
            a121.SessionConfig(
                [
                    {1: a121.SensorConfig()},
                    {2: a121.SensorConfig()},
                    {3: a121.SensorConfig()},
                    {4: a121.SensorConfig()},
                ]
            ),
            {
                1: calibration,
                3: calibration,
            },
        )

        calibrations_provided = client.calibrations_provided
        assert 1 in calibrations_provided
        assert 2 in calibrations_provided
        assert 3 in calibrations_provided
        assert 4 in calibrations_provided

        assert calibrations_provided[1]
        assert not calibrations_provided[2]
        assert calibrations_provided[3]
        assert not calibrations_provided[4]

    def test_recording_with_calibration_provided(self, client, tmp_h5_file_path):
        calibrations = client.calibrations
        assert calibrations

        calibration = calibrations.get(1)
        assert calibration

        client.setup_session(
            a121.SessionConfig(
                [
                    {1: a121.SensorConfig()},
                    {2: a121.SensorConfig()},
                    {3: a121.SensorConfig()},
                    {4: a121.SensorConfig()},
                ]
            ),
            {
                2: calibration,
                4: calibration,
            },
        )

        _ = a121.H5Recorder(tmp_h5_file_path, client)
        client.start_session()
        [client.get_next() for _ in range(5)]
        client.stop_session()

        record = a121.load_record(tmp_h5_file_path)
        assert 2 in record.calibrations
        assert 4 in record.calibrations

        setup_calibrations = client.calibrations
        for sensor_id in setup_calibrations:
            assert sensor_id in record.calibrations
            assert setup_calibrations[sensor_id].data == record.calibrations[sensor_id].data
            assert (
                setup_calibrations[sensor_id].temperature
                == record.calibrations[sensor_id].temperature
            )

        assert not record.calibrations_provided[1]
        assert record.calibrations_provided[2]
        assert not record.calibrations_provided[3]
        assert record.calibrations_provided[4]


class TestAStartedClient(CannotPlayAroundWithRecorder):
    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            yield c

    @pytest.fixture
    def client_with_recorder(self, client_kwargs, tmp_h5_file_path):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            _ = a121.H5Recorder(tmp_h5_file_path, c)
            c.start_session()
            yield c

        tmp_h5_file_path.unlink()

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert client.session_is_started

    def test_can_get_next(self, client):
        _ = client.get_next()

    def test_returns_the_same_results_that_are_recorded(
        self, client_with_recorder: a121.Client, tmp_h5_file_path
    ):
        results = [client_with_recorder.get_next() for _ in range(5)]
        client_with_recorder.stop_session()
        record = a121.load_record(tmp_h5_file_path)

        for result_a, result_b in zip(record.results, results):
            assert result_a == result_b

    def test_can_stop(self, client):
        client.stop_session()
        assert not client.session_is_started

    def test_cannot_start_again(self, client_with_recorder):
        with pytest.raises(ClientError):
            client_with_recorder.start_session()

    def test_can_stop_and_start_to_create_new_sessions_in_the_recorder(
        self, client_with_recorder, tmp_h5_file_path
    ):
        num_additional_sessions = 3
        for _ in range(num_additional_sessions):
            client_with_recorder.stop_session()
            client_with_recorder.start_session()

        client_with_recorder.stop_session()
        assert (
            a121.load_record(tmp_h5_file_path).num_sessions
            == a121.open_record(tmp_h5_file_path).num_sessions
            == (num_additional_sessions + 1)
        )


class TestAStoppedClient(TestASetupClient):
    """A stopped client should have the same behaviour as it had when first set up"""

    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            c.stop_session()
            yield c


class TestAStoppedAndSetupClient(TestASetupClient):
    """A stopped client that was later setup
    should have the same behaviour as a setup client.
    """

    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            c.stop_session()
            c.setup_session(a121.SessionConfig())
            yield c


class TestAStoppedAndSetupAndStartedClient(TestAStartedClient):
    """A client that has been started twice
    should have the same behaviour as client that has been started once.
    """

    @pytest.fixture
    def client(self, client_kwargs):
        with a121.Client.open(**client_kwargs) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            c.stop_session()
            c.setup_session(a121.SessionConfig())
            c.start_session()
            yield c


class TestADisconnectedClient(TestAClosedClient):
    """A disconnected client should have the same behaviour as a fresh, unconnected client."""

    @pytest.fixture
    def client(self, client_kwargs):
        c = a121.Client.open(**client_kwargs)
        c.setup_session(a121.SessionConfig())
        c.start_session()
        c.stop_session()
        c.close()

        yield c
        if c.connected:
            c.close()
