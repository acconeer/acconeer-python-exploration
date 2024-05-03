# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import os
import sys

import pytest


sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))


def pytest_addoption(parser):
    parser.addoption(
        "--uart",
        dest="uart",
        metavar="port",
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

    parser.addoption(
        "--update-outputs",
        dest="update_outputs",
        action="store_true",
        help="Update output files.",
    )


def ids_fun(setup):
    try:
        return setup[0]
    except Exception:
        return ""


@pytest.fixture(scope="session")
def should_update_outputs(request):
    return request.config.getoption("--update-outputs") is True
