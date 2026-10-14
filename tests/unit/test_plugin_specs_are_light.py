# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import subprocess
import sys


_SPECS = "acconeer.exptool.a121.algo._plugin_specs"
_ALGO = "acconeer.exptool.a121.algo"
_LIGHT_ALGO_MODULES = {"_plugin_specs", "_base", "_utils"}

_LIST_MODULES_AFTER_IMPORTING_SPECS = f"""
import importlib, pkgutil, sys
import {_SPECS} as specs
for module in pkgutil.iter_modules(specs.__path__):
    importlib.import_module(f"{_SPECS}.{{module.name}}")
print("\\n".join(sys.modules))
"""


def test_importing_plugin_specs_loads_no_algorithm_implementation() -> None:
    # A fresh interpreter, since this one has imported algorithms already
    loaded = subprocess.run(
        [sys.executable, "-c", _LIST_MODULES_AFTER_IMPORTING_SPECS],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()

    heavy = sorted(
        name
        for name in loaded
        if name.startswith(f"{_ALGO}.")
        and name.split(".")[len(_ALGO.split("."))] not in _LIGHT_ALGO_MODULES
    )

    assert heavy == [], (
        "Plugin specs must import algorithm implementations inside the "
        "create_*_plugin methods, not at module level"
    )
