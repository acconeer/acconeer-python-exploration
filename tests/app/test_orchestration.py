# Copyright (c) Acconeer AB, 2026
# All rights reserved

import subprocess as sp
from pathlib import Path

import pytest


A121_PLUGIN_KEYS = sp.check_output(
    "python -m acconeer.exptool.app.new --list-plugin-modules --generation a121".split(),
    text=True,
).split()


@pytest.mark.parametrize("plugin_key", A121_PLUGIN_KEYS)
def test_error_popup_a121(plugin_key: str, tmp_path: Path) -> None:
    et_opts = [
        "-v",
        *("--data-dir", str(tmp_path)),
        "--dump-exceptions",
        "--no-port-updater",
        *("--generation", "a121"),
        *("--plugin-key", plugin_key),
        "--simulated-autoconnect",
        *("--tasks", "pseudo:quit"),
    ]

    sp.check_call(
        [
            "sh",
            "-x",
            "-c",
            f"timeout 10 python -m acconeer.exptool.app.new {' '.join(et_opts)}",
        ]
    )
