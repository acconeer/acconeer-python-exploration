# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import subprocess
import sys

import pytest


_LIGHT_ALGO_MODULES = {"_plugin_specs", "_base", "_utils"}

_LIST_MODULES_AFTER_IMPORTING_SPECS = """
import importlib, pkgutil, sys
specs_name = sys.argv[1]
specs = importlib.import_module(specs_name)
for module in pkgutil.iter_modules(specs.__path__):
    importlib.import_module(f"{specs_name}.{module.name}")
print("\\n".join(sys.modules))
"""


@pytest.mark.parametrize("algo", ["acconeer.exptool.a121.algo", "acconeer.exptool.a2.algo"])
def test_importing_plugin_specs_loads_no_algorithm_implementation(algo: str) -> None:
    # A fresh interpreter, since this one has imported algorithms already
    loaded = subprocess.run(
        [sys.executable, "-c", _LIST_MODULES_AFTER_IMPORTING_SPECS, f"{algo}._plugin_specs"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()

    heavy = sorted(
        name
        for name in loaded
        if name.startswith(f"{algo}.")
        and name.split(".")[len(algo.split("."))] not in _LIGHT_ALGO_MODULES
    )

    assert heavy == [], (
        "Plugin specs must import algorithm implementations inside the "
        "create_*_plugin and replay_dialog_* methods, not at module level"
    )
