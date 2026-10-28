# Copyright (c) Acconeer AB, 2026
# All rights reserved

# Loaded with -p, as pytest 9 reads the values of options it doesn't know yet
# as test paths (pytest-dev/pytest#13913).

from pathlib import Path

import pytest


def _existing_path(path_str: str) -> Path:
    p = Path(path_str)
    if not p.exists():
        msg = f"Could not find '{p}'."
        raise FileNotFoundError(msg)
    return p


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
        "--a2-exploration-server-paths",
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

    parser.addoption(
        "--a2-sensor-current-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--a2-timing-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--a2-computation-time-limits-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption(
        "--a2-memory-usage-path",
        nargs="*",
        type=_existing_path,
        default=[],
    )

    parser.addoption("--test-devsite", action="store_true")

    parser.addoption(
        "--algo-bundle",
        type=_existing_path,
        help="Installs this algo bundle zip, for the tests marked algo_bundle.",
    )

    parser.addoption(
        "--dangerously-skip-integrity-check",
        action="store_true",
        help="Installs a '--algo-bundle' zip that this release doesn't expect.",
    )

    parser.addoption(
        "--plot-show",
        action="store_true",
        default=False,
        help="Show plots after each test.",
    )

    parser.addoption(
        "--plot-show-on-fail",
        action="store_true",
        default=False,
        help="Show plots after a test failure.",
    )
