# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import pytest

from acconeer.exptool import a2
from acconeer.exptool._core.communication import ClientError
from acconeer.exptool._core.entities.client_info import ClientInfo, SocketInfo
from acconeer.exptool.a2._core.communication import ExplorationClient


_LOW_UPDATE_RATE = 10  # Hz
_SESSION_CONFIG_W_LOW_UPDATE_RATE = a2.SessionConfig(
    sensor_configs=[a2.SensorConfig.single_subsweep()],
    update_rate=_LOW_UPDATE_RATE,
)


@pytest.fixture(params=["socket", "mock"], ids=str)
def blank_client(worker_tcp_port, request, a2_exploration_server):
    if request.param == "socket":
        return ExplorationClient(
            ClientInfo(
                socket=SocketInfo(
                    ip_address="localhost",
                    tcp_port=worker_tcp_port,
                ),
            ),
            enable_diagnostics=False,
        )
    elif request.param == "mock":
        return a2.Client.open(mock=True)
    else:
        assert False


@pytest.fixture
def tmp_h5_file_path(tmp_path):
    return tmp_path / "record.h5"


@pytest.fixture
def h5_recorder(tmp_h5_file_path):
    with a2.H5Recorder(tmp_h5_file_path) as recorder:
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
    def client(self, blank_client):
        c = blank_client
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
            _ = client.tick_period


class TestAConnectedClient(CanAttachAndDetachRecorder):
    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
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
            _ = client.tick_period


class TestASetupClient(CanAttachAndDetachRecorder):
    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            yield c

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert not client.session_is_started

    def test_can_access_all_data_structures(self, client):
        _ = client.server_info
        _ = client.session_config
        _ = client.tick_period

    def test_no_data_structures_are_none(self, client):
        assert client.server_info is not None
        assert client.session_config is not None
        assert client.tick_period is not None

    def test_cannot_get_next(self, client):
        with pytest.raises(ClientError):
            _ = client.get_next()

    def test_can_be_setup_again(self, client):
        client.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)


class TestAStartedClient(CannotPlayAroundWithRecorder):
    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            c.start_session()
            yield c

    @pytest.fixture
    def client_with_recorder(self, blank_client, tmp_h5_file_path):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            _ = a2.H5Recorder(tmp_h5_file_path, c)
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
        self, client_with_recorder: a2.Client, tmp_h5_file_path
    ):
        results = [
            client_with_recorder.get_next(format=a2.Client.ResultFormat.FULL) for _ in range(5)
        ]
        client_with_recorder.stop_session()
        record = a2.open_record(tmp_h5_file_path)

        for result_a, result_b in zip(record.group_results, results):
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
            a2.open_record(tmp_h5_file_path).num_sessions
            == a2.open_record(tmp_h5_file_path).num_sessions
            == (num_additional_sessions + 1)
        )


class TestAStoppedClient(TestASetupClient):
    """A stopped client should have the same behaviour as it had when first set up"""

    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            c.start_session()
            c.stop_session()
            yield c


class TestAStoppedAndSetupClient(TestASetupClient):
    """A stopped client that was later setup
    should have the same behaviour as a setup client.
    """

    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            c.start_session()
            c.stop_session()
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            yield c


class TestAStoppedAndSetupAndStartedClient(TestAStartedClient):
    """A client that has been started twice
    should have the same behaviour as client that has been started once.
    """

    @pytest.fixture
    def client(self, blank_client):
        with blank_client as c:
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            c.start_session()
            c.stop_session()
            c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
            c.start_session()
            yield c


class TestADisconnectedClient(TestAClosedClient):
    """A disconnected client should have the same behaviour as a fresh, unconnected client."""

    @pytest.fixture
    def client(self, blank_client):
        c = blank_client
        c.setup_session(_SESSION_CONFIG_W_LOW_UPDATE_RATE)
        c.start_session()
        c.stop_session()
        c.close()

        yield c
        if c.connected:
            c.close()
