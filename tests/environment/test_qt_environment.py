# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import subprocess as sp
from pathlib import Path

import pytest


# Each test gets its own envs through --data-dir, so none runs in an env that
# another xdist worker is still creating.


@pytest.mark.parametrize(
    "cmd",
    [
        "run python -c 'import acconeer.exptool'",
        "run app:python -c 'import acconeer.exptool'",
    ],
)
def test_pyside6_or_no_bindings_does_not_mention_conflicting_bindings_on_stdout(
    cmd: str, tmp_path: Path
) -> None:
    output = sp.check_output(f"hatch --data-dir {tmp_path} {cmd}", text=True, shell=True)
    assert "Found conflicting Qt binding" not in output


@pytest.mark.parametrize(
    "cmd",
    [
        "run default:python -m acconeer.exptool.app",
        "run default:python -m acconeer.exptool.app.new",
    ],
)
def test_trying_to_run_et_without_app_extra_fails_and_mentions_app_extra(
    cmd: str, tmp_path: Path
) -> None:
    completed_process = sp.run(
        f"hatch --data-dir {tmp_path} {cmd}", stdout=sp.PIPE, text=True, shell=True
    )
    assert "[app]" in completed_process.stdout
    assert completed_process.returncode != 0


@pytest.mark.parametrize(
    "cmd",
    [
        "run test-multiple-qt-bindings:python -c 'import acconeer.exptool'",
    ],
)
def test_multiple_qt_bindings_in_environment_mentions_conflicting_bindings_on_stdout(
    cmd: str, tmp_path: Path
) -> None:
    output = sp.check_output(f"hatch --data-dir {tmp_path} {cmd}", text=True, shell=True)
    assert "Found conflicting Qt binding 'PyQt6'" in output
    assert "Found conflicting Qt binding 'PyQt5'" in output
    assert "Found conflicting Qt binding 'PySide2'" in output
