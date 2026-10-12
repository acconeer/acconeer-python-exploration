# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import importlib
import importlib.machinery
import shutil
import warnings
import zipfile
from pathlib import Path, PurePosixPath


_PARENT_BY_MODULE: dict[str, str] = {}


def install_module_bundle(zip_path: Path, base_extract_dir: Path) -> None:
    """Extracts ``zip_path`` and imports each member as a submodule of its package."""
    extract_module_bundle(zip_path, base_extract_dir)
    import_module_bundle(base_extract_dir)


def extract_module_bundle(zip_path: Path, base_extract_dir: Path) -> None:
    """Extracts ``zip_path`` into ``base_extract_dir``, refusing unknown members."""
    with zipfile.ZipFile(zip_path) as zf:
        for filename in zf.namelist():
            path = PurePosixPath(filename)
            module = path.name.split(".")[0]
            member = str(path.parent / module)
            if member not in _PARENT_BY_MODULE:
                msg = f"Bundle member {filename!r} is not a known module."
                warnings.warn(msg)
                continue

            parent_dir = _extract_dir(base_extract_dir, _PARENT_BY_MODULE[member])
            _raise_if_shadowed(module, _PARENT_BY_MODULE[member], parent_dir)
            parent_dir.mkdir(parents=True, exist_ok=True)
            with zf.open(filename) as src, (parent_dir / path.name).open("wb") as out:
                shutil.copyfileobj(src, out)


def import_module_bundle(base_extract_dir: Path) -> None:
    """Imports each module extracted by ``extract_module_bundle`` as a submodule of its package."""
    # Every parent's __path__ is extended before any import happens below, so a
    # module that depends on a sibling under a different parent still resolves.
    for parent in set(_PARENT_BY_MODULE.values()):
        parent_pkg = importlib.import_module(parent)
        search_dir = str(_extract_dir(base_extract_dir, parent))
        if search_dir not in parent_pkg.__path__:
            parent_pkg.__path__.append(search_dir)

    for member, parent in _PARENT_BY_MODULE.items():
        importlib.import_module(f"{parent}.{PurePosixPath(member).name}")


def _raise_if_shadowed(module: str, parent: str, parent_dir: Path) -> None:
    # The bundle's directory is appended to the parent's __path__, so a module
    # of the same name anywhere else on that path is imported instead.
    other_dirs = [p for p in importlib.import_module(parent).__path__ if p != str(parent_dir)]
    spec = importlib.machinery.PathFinder.find_spec(module, other_dirs)
    if spec is not None:
        msg = (
            f"{spec.origin} would shadow {module!r} from the bundle. "
            "Remove it and install the bundle again"
        )
        raise ValueError(msg)


def _extract_dir(base_extract_dir: Path, parent: str) -> Path:
    return base_extract_dir / parent.replace(".", "_")
