def pytest_addoption(parser):
    parser.addoption(
            "--uart",
            dest="uart",
            metavar="port",
            nargs="?",
            const="",
            )

    parser.addoption(
            "--spi",
            dest="spi",
            action="store_true",
            )

    parser.addoption(
            "--socket",
            dest="socket",
            metavar="socket_args",
            nargs=2,
            )


def pytest_generate_tests(metafunc):
    FIXTURE_NAME = "setup"

    if FIXTURE_NAME in metafunc.fixturenames:
        params = []

        uart_port = metafunc.config.getoption("uart")
        if uart_port is not None:
            params.append(("uart", uart_port))

        spi = metafunc.config.getoption("spi")
        if spi:
            params.append(("spi", ))

        socket = metafunc.config.getoption("socket")
        if socket is not None:
            params.append(("socket", *socket))

        metafunc.parametrize(FIXTURE_NAME, params, indirect=True)
