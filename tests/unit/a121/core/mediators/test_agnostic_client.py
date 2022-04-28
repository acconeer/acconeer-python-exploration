from unittest.mock import Mock, call

import numpy as np
import pytest

from acconeer.exptool.a121._core._entities import (
    Metadata,
    SensorConfig,
    SensorDataType,
    ServerInfo,
    SessionConfig,
)
from acconeer.exptool.a121._core._mediators import AgnosticClient, ClientError


@pytest.fixture(scope="function")
def mock_link():
    return Mock()


@pytest.fixture
def metadata():
    return Metadata(
        frame_data_length=1,
        sweep_data_length=1,
        subsweep_data_length=np.array([1]),
        subsweep_data_offset=np.array([0]),
        data_type=SensorDataType.INT_16_COMPLEX,
    )


@pytest.fixture
def mock_communication_protocol(metadata):
    mock_comm_p = Mock()
    mock_comm_p.get_system_info_command.return_value = b"get_system_info"
    mock_comm_p.get_system_info_response.return_value = ServerInfo(
        rss_version="rss_version", sensor_count=1, ticks_per_second=1
    )

    mock_comm_p.get_sensor_info_command.return_value = b"get_sensor_info"
    mock_comm_p.get_sensor_info_response.return_value = [1]

    mock_comm_p.setup_command.return_value = b"setup"
    mock_comm_p.setup_response.return_value = [{1: metadata}]

    mock_comm_p.start_streaming_command.return_value = b"start_streaming"
    mock_comm_p.start_streaming_response.return_value = True

    mock_comm_p.stop_streaming_command.return_value = b"stop_streaming"
    mock_comm_p.stop_streaming_response.return_value = True

    mock_comm_p.get_next_header.return_value = (0, [])
    mock_comm_p.get_next_payload.return_value = []
    return mock_comm_p


@pytest.fixture(scope="function")
def clean_client_and_link(mock_link, mock_communication_protocol):
    return AgnosticClient(mock_link, mock_communication_protocol), mock_link


@pytest.fixture(scope="function")
def connected_client_and_link(clean_client_and_link):
    client, link = clean_client_and_link
    client.connect()
    return client, link


@pytest.fixture(scope="function")
def setup_client_and_link_and_metadata(connected_client_and_link):
    client, link = connected_client_and_link
    metadata = client.setup_session(SessionConfig(SensorConfig(), extended=True))
    return client, link, metadata


@pytest.fixture(scope="function")
def started_client_and_link(setup_client_and_link_and_metadata):
    client, link, _ = setup_client_and_link_and_metadata
    client.start_session()
    return client, link


@pytest.fixture(scope="function")
def stopped_client_and_link(started_client_and_link):
    client, link = started_client_and_link
    client.stop_session()
    return client, link


@pytest.fixture(scope="function")
def disconnected_client_and_link(stopped_client_and_link):
    client, link = stopped_client_and_link
    client.disconnect()
    return client, link


def test_client_unconnected(clean_client_and_link):
    client, _ = clean_client_and_link
    assert not client.connected
    assert not client.session_is_setup
    assert not client.session_is_started

    with pytest.raises(ClientError):
        _ = client.setup_session(SessionConfig(SensorConfig()))

    with pytest.raises(ClientError):
        client.start_session()

    with pytest.raises(ClientError):
        _ = client.get_next()

    with pytest.raises(ClientError):
        _ = client.server_info

    with pytest.raises(ClientError):
        _ = client.session_config

    with pytest.raises(ClientError):
        _ = client.extended_metadata


def test_client_connected(connected_client_and_link):
    client, mock_link = connected_client_and_link

    mock_link.connect.assert_called_once_with()
    mock_link.send.assert_has_calls(
        [call(b"get_system_info"), call(b"get_sensor_info")], any_order=True
    )

    assert client.connected
    assert not client.session_is_setup
    assert not client.session_is_started

    with pytest.raises(ClientError):
        client.start_session()

    with pytest.raises(ClientError):
        _ = client.get_next()

    _ = client.server_info

    with pytest.raises(ClientError):
        _ = client.session_config

    with pytest.raises(ClientError):
        _ = client.extended_metadata


def test_client_setup(setup_client_and_link_and_metadata, metadata):
    client, mock_link, actual_metadata = setup_client_and_link_and_metadata
    expected_metadata = metadata

    # On setup, the client is supposed to send the appropriate config via the link
    # And recieve some metadata
    assert actual_metadata == [{1: expected_metadata}]
    mock_link.send.assert_called_with(b"setup")
    assert client.session_is_setup

    with pytest.raises(ClientError):
        _ = client.get_next()

    _ = client.server_info
    _ = client.session_config
    _ = client.extended_metadata


def test_client_started(started_client_and_link):
    client, mock_link = started_client_and_link

    # When starting a session
    mock_link.send.assert_called_with(b"start_streaming")
    assert client.session_is_started

    # `get_next` should work at this point
    result = client.get_next()
    assert result == []


def test_client_stop_session(stopped_client_and_link):
    client, mock_link = stopped_client_and_link

    mock_link.send.assert_called_with(b"stop_streaming")
    assert not client.session_is_started


def test_client_disconnect(disconnected_client_and_link):
    client, mock_link = disconnected_client_and_link

    mock_link.disconnect.assert_called_once_with()
    assert not client.connected
