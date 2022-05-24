from acconeer.exptool import a121


def test_can_connect():
    with a121.Client(ip_address="localhost") as client:
        assert client.connected
