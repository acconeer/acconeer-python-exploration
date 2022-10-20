# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import pytest

from acconeer.exptool import a121


CLIENT_KWARGS = dict(ip_address="localhost")


class TestAnUnconnectedClient:
    @pytest.fixture
    def client(self):
        c = a121.Client(**CLIENT_KWARGS)
        yield c
        if c.connected:
            c.disconnect()

    def test_reports_correct_statuses(self, client):
        assert not client.connected
        assert not client.session_is_setup
        assert not client.session_is_started

    def test_can_connect(self, client):
        client.connect()

    def test_can_be_setup(self, client):
        _ = client.setup_session(a121.SessionConfig())

    def test_setup_session_autoconnects(self, client):
        _ = client.setup_session(a121.SessionConfig())
        assert client.connected

    def test_cannot_be_started(self, client):
        with pytest.raises(a121.ClientError):
            client.start_session()

    def test_cannot_get_next_result(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.get_next()

    def test_doesnt_have_server_info(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.server_info

    def test_doesnt_have_session_config(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.session_config

    def test_doesnt_have_any_metadata(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.extended_metadata


class TestAConnectedClient:
    @pytest.fixture
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
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
        with pytest.raises(a121.ClientError):
            client.start_session()

    def test_cannot_get_next(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.get_next()

    def test_cannot_access_session_config(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.session_config

    def test_cannot_access_metadata(self, client):
        with pytest.raises(a121.ClientError):
            _ = client.extended_metadata


class TestASetupClient:
    @pytest.fixture
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
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
        with pytest.raises(a121.ClientError):
            _ = client.get_next()

    def test_can_be_setup_again(self, client):
        old_metadata = client.extended_metadata
        client.setup_session(
            a121.SensorConfig(
                sweeps_per_frame=client.session_config.sensor_config.sweeps_per_frame + 1
            )
        )
        assert old_metadata != client.extended_metadata


class TestAStartedClient:
    @pytest.fixture
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            yield c

    @pytest.fixture
    def tmp_h5_file_path(self, tmp_path):
        return tmp_path / "record.h5"

    @pytest.fixture
    def client_with_recorder(self, tmp_h5_file_path):
        with a121.Client(**CLIENT_KWARGS) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session(recorder=a121.H5Recorder(tmp_h5_file_path))
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


class TestAStoppedClient(TestAConnectedClient):
    """A stopped client should have the same behaviour as a newly connected client."""

    @pytest.fixture
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            c.stop_session()
            yield c


class TestAStoppedAndSetupClient(TestASetupClient):
    """A stopped client that was later setup
    should have the same behaviour as a setup client.
    """

    @pytest.fixture
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
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
    def client(self):
        with a121.Client(**CLIENT_KWARGS) as c:
            c.setup_session(a121.SessionConfig())
            c.start_session()
            c.stop_session()
            c.setup_session(a121.SessionConfig())
            c.start_session()
            yield c


class TestADisconnectedClient(TestAnUnconnectedClient):
    """A disconnected client should have the same behaviour as a fresh, unconnected client."""

    @pytest.fixture
    def client(self):
        c = a121.Client(**CLIENT_KWARGS)
        c.connect()
        c.setup_session(a121.SessionConfig())
        c.start_session()
        c.stop_session()
        c.disconnect()

        yield c
        if c.connected:
            c.disconnect()
