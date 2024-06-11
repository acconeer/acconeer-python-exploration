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


def pytest_addoption(parser: pytest.Parser) -> None:
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

    parser.addoption(
        "--sensor-current-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--module-current-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--inter-sweep-idle-state-current-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--memory-usage-path",
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

    if "sensor_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--sensor-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 sensor current limits"),
        )
        metafunc.parametrize(argnames="sensor_current_limits_path", argvalues=values)

    if "module_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--module-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 module current limits"),
        )
        metafunc.parametrize(argnames="module_current_limits_path", argvalues=values)

    if "inter_sweep_idle_state_current_limits_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--inter-sweep-idle-state-current-limits-path", []),
            err_msg=err_msg_fmt.format("A121 inter sweep idle state current limits"),
        )
        metafunc.parametrize(
            argnames="inter_sweep_idle_state_current_limits_path", argvalues=values
        )

    if "memory_usage_path" in metafunc.fixturenames:
        values = _validate_parametrization(
            metafunc.config.getoption("--memory-usage-path", []),
            err_msg=err_msg_fmt.format("A121 memory usage"),
        )
        metafunc.parametrize(argnames="memory_usage_path", argvalues=values)


@pytest.fixture(scope="session")
def should_update_outputs(request):
    return request.config.getoption("--update-outputs") is True
