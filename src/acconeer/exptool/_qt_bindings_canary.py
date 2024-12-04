# Copyright (c) Acconeer AB, 2024
# All rights reserved

"""
This module does a best effort to warn the user of there being
multiple Qt bindings installed in the current Python environment,
prompting them to resolve the issue.
"""

import importlib.metadata


_WARNING_FMT = """\
============================================= WARNING ==============================================
Found conflicting Qt binding '{binding_module_name}'.

Exploration Tool might not function properly with it installed.

Resolve the issue by either:

- Installing Exploration Tool in a virtualenv.
  See https://packaging.python.org/en/latest/guides/installing-using-pip-and-virtual-environments/

- Uninstall '{binding_module_name}' with the command
  * pip uninstall {binding_module_name}  (Windows)
  * pip3 uninstall {binding_module_name} (Linux)
===================================================================================================
"""


try:
    import PySide6  # noqa: F401
except ImportError:
    pass  # Did not find installed PySide6 (which is OK)

for disallowed_binding in ["PyQt6", "PyQt5", "PySide2"]:
    try:
        _ = importlib.metadata.version(disallowed_binding)
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        print(_WARNING_FMT.format(binding_module_name=disallowed_binding))
