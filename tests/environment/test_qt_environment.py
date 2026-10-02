# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import os
import shlex
import subprocess as sp
import sys
from pathlib import Path

import pytest


# Each test gets its own envs through --data-dir, so none runs in an env that
# another xdist worker is still creating.

# A PyApp-built hatch (the official installers) exports its own path as PYAPP.
# Inside a hatch env on Windows, the "hatch" first on PATH is the entry point in
# PyApp's private Python instead, which can fail to start
# ("uv trampoline failed to load trampoline kind from resources").
HATCH = os.environ.get("PYAPP", "hatch") if sys.platform == "win32" else "hatch"


@pytest.mark.parametrize(
    "args",
    [
        ["run", "python", "-c", "import acconeer.exptool"],
        ["run", "app:python", "-c", "import acconeer.exptool"],
    ],
    ids=shlex.join,
)
def test_pyside6_or_no_bindings_does_not_mention_conflicting_bindings_on_stdout(
    args: list[str], tmp_path: Path
) -> None:
    output = sp.check_output([HATCH, "--data-dir", str(tmp_path), *args], text=True)
    assert "Found conflicting Qt binding" not in output


@pytest.mark.parametrize(
    "args",
    [
        ["run", "default:python", "-m", "acconeer.exptool.app"],
        ["run", "default:python", "-m", "acconeer.exptool.app.new"],
    ],
    ids=shlex.join,
)
def test_trying_to_run_et_without_app_extra_fails_and_mentions_app_extra(
    args: list[str], tmp_path: Path
) -> None:
    completed_process = sp.run(
        [HATCH, "--data-dir", str(tmp_path), *args], stdout=sp.PIPE, text=True
    )
    assert "[app]" in completed_process.stdout
    assert completed_process.returncode != 0


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="PySide2 has no Windows wheels, so the test-multiple-qt-bindings env can't be built",
)
@pytest.mark.parametrize(
    "args",
    [
        ["run", "test-multiple-qt-bindings:python", "-c", "import acconeer.exptool"],
    ],
    ids=shlex.join,
)
def test_multiple_qt_bindings_in_environment_mentions_conflicting_bindings_on_stdout(
    args: list[str], tmp_path: Path
) -> None:
    output = sp.check_output([HATCH, "--data-dir", str(tmp_path), *args], text=True)
    assert "Found conflicting Qt binding 'PyQt6'" in output
    assert "Found conflicting Qt binding 'PyQt5'" in output
    assert "Found conflicting Qt binding 'PySide2'" in output
