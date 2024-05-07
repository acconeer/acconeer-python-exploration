# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

import os
import sys
import typing as t
from pathlib import Path

import pytest


sys.path.append(os.path.join(os.path.dirname(__file__), "helpers"))


def _existing_path(path_str: str) -> Path:
    p = Path(path_str)
    if not p.exists():
        msg = f"Could not find '{p}'."
        raise FileNotFoundError(msg)
    return p


def _validate_parametrization(iterable: t.Sized, err_msg: str) -> t.Sized:
    running_in_jenkins = os.environ.get("CI", False)
    if running_in_jenkins and len(iterable) < 1:
        raise ValueError(err_msg)
    return iterable


def pytest_addoption(parser):
    parser.addoption(
        "--update-outputs",
        dest="update_outputs",
        action="store_true",
        help="Update output files.",
    )

    parser.addoption(
        "--a121-exploration-server-paths",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--a111-exploration-server-paths",
        nargs="*",
        type=_existing_path,
        default=[],
    )


def pytest_generate_tests(metafunc):
    # This function dynamically parametrizes tests/fixtures based on CLI arguments.
    # See https://docs.pytest.org/en/latest/how-to/parametrize.html#basic-pytest-generate-tests-example

    err_msg_fmt = "Need to specify at least 1 {} when running in Jenkins."

    if "a111_exploration_server_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a111-exploration-server-paths", []),
            err_msg=err_msg_fmt.format("A111 Exploration Server"),
        )
        metafunc.parametrize(argnames="a111_exploration_server_path", argvalues=values)

    if "a121_exploration_server_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--a121-exploration-server-paths", []),
            err_msg=err_msg_fmt.format("A121 Exploration Server"),
        )
        metafunc.parametrize(argnames="a121_exploration_server_path", argvalues=values)


def ids_fun(setup):
    try:
        return setup[0]
    except Exception:
        return ""


@pytest.fixture(scope="session")
def should_update_outputs(request):
    return request.config.getoption("--update-outputs") is True
