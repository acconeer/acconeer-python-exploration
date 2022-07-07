from unittest.mock import DEFAULT, Mock, call

import numpy as np
import pytest

from acconeer.exptool.a121._core.entities import Metadata, SensorInfo, ServerInfo, SessionConfig
from acconeer.exptool.a121._core.mediators import AgnosticClient, ClientError


@pytest.fixture
def metadata():
    return Metadata(
        frame_data_length=1,
        sweep_data_length=1,
        subsweep_data_length=np.array([1]),
        subsweep_data_offset=np.array([0]),
        calibration_temperature=0,
        tick_period=0,
        base_step_length_m=0,
        max_sweep_rate=0,
    )


@pytest.fixture
def mock_protocol(metadata):
    def mock_get_next_header(bytes_, extended_metadata, ticks_per_second):
        if bytes_ == b"data_header":
            return DEFAULT

        raise Exception

    class MockCommunicationProtocol:
        end_sequence = b""
        get_system_info_command = Mock(return_value=b"get_system_info")
        get_system_info_response = Mock(
            return_value=(
                ServerInfo(
                    rss_version="rss_version",
                    sensor_count=1,
                    ticks_per_second=1,
                    sensor_infos={1: SensorInfo(connected=True)},
                ),
                "a121",
            )
        )
        get_sensor_info_command = Mock(return_value=b"get_sensor_info")
        get_sensor_info_response = Mock(return_value=[1])
        setup_command = Mock(return_value=b"setup")
        setup_response = Mock(return_value=[{1: metadata}])
        start_streaming_command = Mock(return_value=b"start_streaming")
        start_streaming_response = Mock(return_value=True)
        stop_streaming_command = Mock(return_value=b"stop_streaming")
        stop_streaming_response = Mock(return_value=True)
        get_next_header = Mock(return_value=(0, []), side_effect=mock_get_next_header)
        get_next_payload = Mock(return_value=[])

    return MockCommunicationProtocol()


class TestAnUnconnectedClient:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        return client

    def test_reports_correct_statuses(self, client):
        assert not client.connected
        assert not client.session_is_setup
        assert not client.session_is_started

    def test_can_connect(self, client):
        client.connect()

    def test_can_be_setup(self, client):
        _ = client.setup_session(SessionConfig(extended=True))

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


class TestAConnectedClient:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        client.connect()
        return client

    def test_connects_link(self, link):
        link.connect.assert_called_once_with()

    def test_sends_get_server_info_commands(self, link):
        link.send.assert_has_calls(
            [call(b"get_system_info"), call(b"get_sensor_info")], any_order=True
        )

    def test_can_access_server_info(self, client):
        _ = client.server_info

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


class Test_a_setup_client:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        client.connect()
        client.setup_session(SessionConfig(extended=True))
        return client

    def test_sends_setup_command_to_link(self, link):
        link.send.assert_called_with(b"setup")

    def test_has_correct_metadata(self, client, metadata):
        assert client.extended_metadata == [{1: metadata}]

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert not client.session_is_started

    def test_can_access_all_data_structures(self, client):
        _ = client.server_info
        _ = client.session_config
        _ = client.extended_metadata

    def test_cannot_get_next(self, client):
        with pytest.raises(ClientError):
            _ = client.get_next()


class TestAStartedClient:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.timeout = 2
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        client.connect()
        client.setup_session(SessionConfig(extended=True))
        client.start_session()
        return client

    def test_sends_start_streaming_command_to_link(self, link):
        link.send.assert_called_with(b"start_streaming")

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert client.session_is_started

    def test_can_get_next(self, client):
        result = client.get_next()
        assert result == []

    @pytest.mark.parametrize(
        "recv_until_buffer",
        [
            [b"end"],
            [b"data_header", b"end"],
            [b"data_header", b"data_header", b"end"],
        ],
        ids=str,
    )
    def test_can_stop(self, link, client, recv_until_buffer, mock_protocol):
        link.recv_until.reset_mock()

        link.recv_until.side_effect = recv_until_buffer
        client.stop_session()

        assert mock_protocol.get_next_header.call_count == len(recv_until_buffer)
        assert link.recv_until.call_count == len(recv_until_buffer)
        mock_protocol.stop_streaming_response.assert_called_once_with(b"end")


class TestAStoppedClient:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.timeout = 2
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        client.connect()
        client.setup_session(SessionConfig(extended=True))
        client.start_session()
        client.stop_session()
        return client

    def test_sends_stop_streaming_command_to_link(self, link):
        link.send.assert_called_with(b"stop_streaming")

    def test_reports_correct_statuses(self, client):
        assert client.connected
        assert client.session_is_setup
        assert not client.session_is_started


class TestADisconnectedClient:
    @pytest.fixture
    def link(self):
        link = Mock()
        link.timeout = 2
        link.recv_until.side_effect = ([b"data_header"] * 20) + [b"stop_streaming"]
        return link

    @pytest.fixture(autouse=True)
    def client(self, link, mock_protocol):
        client = AgnosticClient(link, mock_protocol)
        client.connect()
        client.setup_session(SessionConfig(extended=True))
        client.start_session()
        client.stop_session()
        client.disconnect()
        return client

    def test_reports_correct_statuses(self, client):
        assert not client.connected
        assert client.session_is_setup
        assert not client.session_is_started

    def test_disconnects_link(self, link):
        link.disconnect.assert_called_once_with()
