# Copyright (c) Acconeer AB, 2026
# All rights reserved

import collections
import subprocess as sp
from pathlib import Path

import pytest

from acconeer.exptool.app.new import plugin_loader


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


@pytest.mark.parametrize(
    "plugin_spec",
    plugin_loader.load_plugins(),
    ids=lambda ps: f"{ps.generation.value}-{ps.key}",
)
def test_error_popup(plugin_spec: plugin_loader.PluginSpec, tmp_path: Path) -> None:
    tasks_key = (plugin_spec.generation.value, plugin_spec.key)
    if tasks_key == ("a121", "bilateration"):
        pytest.skip("Bilateration requires unique sensor IDs. Needs to be revisited.")

    if tasks_key == ("a121", "parking"):
        pytest.skip(
            "Raises an error: Could not start, 'NoneType' object has no attribute 'noise_level'"
        )

    tasks = TASK_TABLE[tasks_key]

    et_opts = [
        "-v",
        "--dump-exceptions",
        "--no-port-updater",
        *("--generation", plugin_spec.generation.value),
        *("--plugin-key", plugin_spec.key),
        "--simulated-autoconnect",
        *("--tasks", *tasks),
    ]

    try:
        sp.check_call(
            [
                "sh",
                "-x",
                "-c",
                f"timeout 20 coverage run --parallel-mode --concurrency=multiprocessing -m acconeer.exptool.app.new {' '.join(['--data-dir', str(tmp_path)] + et_opts)}",
            ],
        )
    except sp.CalledProcessError as cpe:
        if cpe.returncode == TIMEOUT_HAPPENED_RETURNCODE:
            msg = (
                "Orchestration test timed out. If testing in parallel, reduce the core count. "
                + "Otherwise increase the timeout for each test"
            )
        else:
            msg = "\n".join(
                [
                    f"An error occured while trying to orchestrate tests for {tasks_key}.",
                    "Maybe some task is missing from TASK_TABLE or something should be changed in the BackendPlugin?",
                    "\nReproduce locally by running:",
                    f"\nhatch run app:new {' '.join(['--data-dir', 'temporary_test_cache'] + et_opts)}",
                ]
            )
        pytest.fail(msg)
