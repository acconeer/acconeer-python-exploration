from typing import List, Type, Union

import pytest

from acconeer.exptool.a111._clients import links
from acconeer.exptool.a111._clients.client_factory import ClientFactory
from acconeer.exptool.a111._clients.json.client import SocketClient
from acconeer.exptool.a111._clients.reg.client import SPIClient, UARTClient


def resolve_attribute_path(obj, attribute_path):
    """
    `attribute_path` should be a path that can be appended to `obj`

    E.g.:

    obj.link.protocol.foo =>
        (obj, attribute_path) = (obj, "link.protocol.foo")
    """
    for attribute in attribute_path.split("."):
        if not attribute:
            continue
        obj = getattr(obj, attribute)
    return obj


def assert_client_types(obj, attribute_path, types: Union[List[Type], Type]):
    """
    `types` is a single type or a list of types, where the attribute
    at `attribute_path` needs to be atleast one of the types.
    """
    obj = resolve_attribute_path(obj, attribute_path)

    if isinstance(types, list):
        assert any([type(obj) == t for t in list(types)])
    else:
        type_ = types
        assert type(obj) == type_


def assert_client_values(obj, attribute_path, value):
    """Analogue to `assert_client_types` but value has no options, hence no list."""
    obj = resolve_attribute_path(obj, attribute_path)
    assert obj == value


def test_conflicting_keyword_arguments_raises_value_error():
    with pytest.raises(ValueError):
        ClientFactory.from_kwargs(**dict(serial_port="port", host="host"))


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(link="socket"),  # only socket no host
        dict(protocol="b", link="socket", host="host"),  # socket, bad protocol
        dict(protocol="b", link="uart", serial_port="port"),  # uart, bad protocol
        dict(link="blablabla"),  # bad link
    ],
)
def test_supplying_weird_arguments_raises_value_error(kwargs):
    with pytest.raises(ValueError):
        ClientFactory.from_kwargs(**kwargs)


@pytest.mark.parametrize(
    "mock_autodetect",
    [[], [("port_a", "tag_a"), ("port_b", "tag_b")]],  # no ports detected  # multiple detected
)
def test_single_acconeer_port_fails(mock_autodetect):
    with pytest.raises(ValueError):
        ClientFactory._get_single_acconeer_module_port(mock_autodetect)


def test_single_acconeer_port_success():
    assert ClientFactory._get_single_acconeer_module_port([("port", "tag")]) == "port"


@pytest.mark.parametrize(
    "kwargs,expected_links_enum",
    [
        (dict(protocol="module"), "uart"),  # Only protocol => infer uart
        (dict(host="mock-host"), "socket"),  # Only host => infer socket
        ({}, "uart"),  # No args -> Infer uart
    ],
)
def test_try_infer_link_from_kwargs(kwargs, expected_links_enum):
    assert ClientFactory._try_infer_link_from_kwargs(**kwargs) == expected_links_enum


@pytest.mark.parametrize("kwargs,expected_protocols_enum", [])  # Nothing here yet
def test_try_infer_protocol_from_kwargs(kwargs, expected_protocols_enum):
    assert ClientFactory._try_infer_protocol_from_kwargs(**kwargs) == expected_protocols_enum


@pytest.mark.parametrize(
    "kwargs,expected_types,expected_values",
    [
        # Only host => infer SocketClient
        (
            dict(host="host"),
            [("", SocketClient), ("_link", links.SocketLink)],
            [("_link._host", "host")],
        ),
        # Exploration over socket
        (
            dict(protocol="exploration", link="socket", host="host"),
            [("", SocketClient), ("_link", links.SocketLink)],
            [("_link._host", "host")],
        ),
        # Exploration over UART
        (
            dict(protocol="exploration", link="uart", serial_port="port"),
            [("", SocketClient), ("_link", links.ExploreSerialLink)],
            [("_link._port", "port")],
        ),
        # Streaming over socket
        (
            dict(protocol="streaming", link="socket", host="host"),
            [("", SocketClient), ("_link", links.SocketLink)],
            [("_link._host", "host")],
        ),
        # Module over UART
        (
            dict(protocol="module", link="uart", serial_port="port"),
            [
                ("", UARTClient),
                ("_link", [links.SerialLink, links.SerialProcessLink]),
            ],
            [("_link._port", "port")],
        ),
        # Module over SPI
        (
            dict(protocol="module", link="spi"),
            [("", SPIClient)],
            [],
        ),
    ],
)
def test_factory(kwargs, expected_types, expected_values):
    client = ClientFactory.from_kwargs(**kwargs)
    for expected_value in expected_values:
        assert_client_values(client, *expected_value)
    for expected_type in expected_types:
        assert_client_types(client, *expected_type)
