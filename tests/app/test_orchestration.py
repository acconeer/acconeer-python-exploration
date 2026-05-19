# Copyright (c) Acconeer AB, 2026
# All rights reserved

import subprocess as sp
from pathlib import Path

import pytest

from acconeer.exptool.app.new import plugin_loader


@pytest.mark.parametrize(
    "plugin_spec",
    plugin_loader.load_plugins(),
    ids=lambda ps: f"{ps.generation.value}-{ps.key}",
)
def test_error_popup(plugin_spec: plugin_loader.PluginSpec, tmp_path: Path) -> None:
    et_opts = [
        "-v",
        *("--data-dir", str(tmp_path)),
        "--dump-exceptions",
        "--no-port-updater",
        *("--generation", plugin_spec.generation.value),
        *("--plugin-key", plugin_spec.key),
        "--simulated-autoconnect",
        *("--tasks", "pseudo:quit"),
    ]

    sp.check_call(
        [
            "sh",
            "-x",
            "-c",
            f"timeout 20 coverage run --parallel-mode --concurrency=multiprocessing -m acconeer.exptool.app.new {' '.join(et_opts)}",
        ]
    )
