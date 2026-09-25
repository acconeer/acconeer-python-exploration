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

    parser.addoption("--test-devsite", action="store_true")
