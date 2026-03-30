# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import subprocess as sp

import pytest


@pytest.mark.parametrize(
    "cmd",
    [
        "hatch run python -c 'import acconeer.exptool'",
        "hatch run app:python -c 'import acconeer.exptool'",
    ],
)
def test_pyside6_or_no_bindings_does_not_mention_conflicting_bindings_on_stdout(
    cmd: str,
) -> None:
    output = sp.check_output(cmd, text=True, shell=True)
    assert "Found conflicting Qt binding" not in output


@pytest.mark.parametrize(
    "cmd",
    [
        "hatch run default:python -m acconeer.exptool.app",
        "hatch run default:python -m acconeer.exptool.app.new",
    ],
)
def test_trying_to_run_et_without_app_extra_fails_and_mentions_app_extra(
    cmd: str,
) -> None:
    completed_process = sp.run(cmd, stdout=sp.PIPE, text=True, shell=True)
    assert "[app]" in completed_process.stdout
    assert completed_process.returncode != 0


@pytest.mark.parametrize(
    "cmd",
    [
        "hatch run test-multiple-qt-bindings:python -c 'import acconeer.exptool'",
    ],
)
def test_multiple_qt_bindings_in_environment_mentions_conflicting_bindings_on_stdout(
    cmd: str,
) -> None:
    output = sp.check_output(cmd, text=True, shell=True)
    assert "Found conflicting Qt binding 'PyQt6'" in output
    assert "Found conflicting Qt binding 'PyQt5'" in output
    assert "Found conflicting Qt binding 'PySide2'" in output
