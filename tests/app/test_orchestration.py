# Copyright (c) Acconeer AB, 2026
# All rights reserved

import collections
import contextlib
import multiprocessing as mp
import shlex
import subprocess as sp
import sys
from pathlib import Path

import pytest

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from acconeer.exptool.app.new import plugin_loader
from acconeer.exptool.app.new.app import (
    _STARTUP_TASKS_GIVE_UP_EXIT_CODE,
    _STARTUP_TASKS_TIMEOUT_S,
    _ExptoolArgumentParser,
    build_main_window,
    load_startup_plugin,
)
from acconeer.exptool.app.new.app_model import app_model as app_model_module
from acconeer.exptool.app.new.backend import MpBackend


TIMEOUT_HAPPENED_RETURNCODE = 124
TYPICAL_TASK_SEQUENCE = ["start_session", "stop_session", "pseudo:quit"]

TASK_TABLE = collections.defaultdict(
    lambda: TYPICAL_TASK_SEQUENCE,
    {
        ("a121", "distance_detector"): ["calibrate_detector", *TYPICAL_TASK_SEQUENCE],
        ("a121", "obstacle_detector"): ["calibrate_detector", *TYPICAL_TASK_SEQUENCE],
        ("a121", "tank_level"): ["calibrate_detector", *TYPICAL_TASK_SEQUENCE],
    },
)

# Longer than the app's own give-up on its startup tasks, so that it gets to report first.
_EXEC_TIMEOUT_S = 3 * _STARTUP_TASKS_TIMEOUT_S


_KNOWN_ISSUES = {
    ("a121", "bilateration"): pytest.mark.skip(
        reason="Bilateration requires unique sensor IDs. Needs to be revisited."
    ),
    ("a121", "parking"): pytest.mark.xfail(
        strict=True,
        reason="Raises an error: Could not start, 'NoneType' object has no attribute 'noise_level'",
    ),
}


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication()


def et_options(plugin_spec: plugin_loader.PluginSpec) -> list[str]:
    tasks_key = (plugin_spec.generation.value, plugin_spec.key)
    return [
        "--dump-exceptions",
        "--no-port-updater",
        *("--generation", plugin_spec.generation.value),
        *("--plugin-key", plugin_spec.key),
        "--simulated-autoconnect",
        *("--tasks", *TASK_TABLE[tasks_key]),
    ]


def reproduce_hint(et_opts: list[str]) -> str:
    return "\n".join(
        [
            "\nReproduce locally by running:",
            f"\nhatch run app:new {shlex.join(['--data-dir', 'temporary_test_cache', *et_opts])}",
        ]
    )


@pytest.mark.parametrize(
    "plugin_spec",
    [
        pytest.param(
            plugin_spec,
            id=f"{plugin_spec.generation.value}-{plugin_spec.key}",
            marks=_KNOWN_ISSUES.get((plugin_spec.generation.value, plugin_spec.key), ()),
        )
        for plugin_spec in plugin_loader.load_plugins()
    ],
)
def test_plugin_runs_startup_tasks(
    plugin_spec: plugin_loader.PluginSpec,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    algo_bundle_extract_dir: Path | None,
) -> None:
    """Runs a session of each plugin as the app would with '--tasks', but in-process."""
    et_opts = et_options(plugin_spec)
    args = _ExptoolArgumentParser().parse_args(et_opts)
    # Children of earlier tests on this worker aren't this test's to blame.
    children_before = set(mp.active_children())
    backend = MpBackend()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: qapp.exit(TIMEOUT_HAPPENED_RETURNCODE))

    # Undone in reverse, and each even if an earlier one fails, so no backend outlives its test.
    with contextlib.ExitStack() as teardown:
        # build_main_window() starts the backend, and may fail after doing so.
        teardown.callback(backend.stop)
        model, main_window = build_main_window(args, plugin_loader.load_plugins(), backend)
        teardown.callback(main_window.close)
        teardown.callback(model.stop)
        teardown.callback(timeout.stop)
        # As in the app, where an exception in a slot counts as an error.
        monkeypatch.setattr(sys, "excepthook", model.excepthook)
        # Stops at the first error, rather than once the unloaded plugin's tasks time out.
        model.sig_error.connect(lambda *_: qapp.exit(1))
        if plugin_spec.requires_algo_bundle_artifact:
            # As the app does at startup, but this process has extracted the bundle already
            monkeypatch.setattr(app_model_module, "install_algo_bundle", lambda *_, **__: None)
            monkeypatch.setattr(
                app_model_module,
                "get_algo_bundle_extract_dir",
                lambda: algo_bundle_extract_dir,
            )
            model.try_install_algo_bundle()

        load_startup_plugin(args, model)
        model.broadcast()
        timeout.start(int(_EXEC_TIMEOUT_S * 1000))
        exit_code = qapp.exec()

    assert not set(mp.active_children()) - children_before, "The backend outlived the app"
    assert model.num_errors == 0, (
        f"{model.num_errors} errors, see the captured output.{reproduce_hint(et_opts)}"
    )
    if exit_code == TIMEOUT_HAPPENED_RETURNCODE:
        pytest.fail(
            f"The tasks did not finish within {_EXEC_TIMEOUT_S} s.{reproduce_hint(et_opts)}"
        )
    elif exit_code == _STARTUP_TASKS_GIVE_UP_EXIT_CODE:
        pytest.fail(
            "The app gave up waiting to become ready to run its startup tasks within"
            + f" app.py's _STARTUP_TASKS_TIMEOUT_S deadline.{reproduce_hint(et_opts)}"
        )


def test_command_line_runs_startup_tasks(tmp_path: Path) -> None:
    """Runs the real entry point, which the in-process test builds around."""
    (plugin_spec,) = [
        p
        for p in plugin_loader.load_plugins()
        if (p.generation.value, p.key) == ("a121", "sparse_iq")
    ]
    et_opts = ["-v", *et_options(plugin_spec)]

    app = [sys.executable, "-m", "acconeer.exptool.app.new", "--data-dir", str(tmp_path), *et_opts]
    try:
        # A covered run measures the app too, through hatch's COVERAGE_PROCESS_START.
        sp.check_call(["sh", "-x", "-c", f"timeout 60 {shlex.join(app)}"])
    except sp.CalledProcessError as cpe:
        if cpe.returncode == TIMEOUT_HAPPENED_RETURNCODE:
            msg = (
                "Orchestration test timed out. If testing in parallel, reduce the core count. "
                + "Otherwise increase the timeout for each test"
            )
        elif cpe.returncode == _STARTUP_TASKS_GIVE_UP_EXIT_CODE:
            msg = (
                "The app gave up waiting to become ready to run its startup tasks within"
                + " app.py's _STARTUP_TASKS_TIMEOUT_S deadline."
                + "\nThis indicates real startup/teardown slowness (e.g. CI load), not a missing task."
                + reproduce_hint(et_opts)
            )
        else:
            msg = (
                f"The app exited with {cpe.returncode}."
                + " Maybe some task is missing from TASK_TABLE or something should be changed"
                + f" in the BackendPlugin?{reproduce_hint(et_opts)}"
            )
        pytest.fail(msg)
