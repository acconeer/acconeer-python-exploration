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

    parser.addoption(
        "--mock",
        dest="mock",
        action="store_true",
    )


def ids_fun(setup):
    try:
        return setup[0]
    except Exception:
        return ""


def pytest_generate_tests(metafunc):
    FIXTURE_NAME = "setup"

    if FIXTURE_NAME in metafunc.fixturenames:
        params = []

        uart_port = metafunc.config.getoption("uart")
        if uart_port is not None:
            params.append(("uart", uart_port))

        spi = metafunc.config.getoption("spi")
        if spi:
            params.append(("spi",))

        socket = metafunc.config.getoption("socket")
        if socket is not None:
            params.append(("socket", *socket))

        mock = metafunc.config.getoption("mock")
        if mock:
            params.append(("mock",))

        metafunc.parametrize(FIXTURE_NAME, params, indirect=True, ids=ids_fun)
