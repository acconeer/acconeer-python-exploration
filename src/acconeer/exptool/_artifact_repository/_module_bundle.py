# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import hashlib
import importlib.machinery
import pkgutil
import shutil
import sys
import zipfile
from collections.abc import Collection
from pathlib import Path, PurePosixPath


# SHA-256 of the module bundle zips that this release accepts
ACCEPTED_DIGESTS: frozenset[str] = frozenset()

_PACKAGES: list[str] = []


class UnexpectedModuleBundleError(ValueError):
    """The module bundle's SHA-256 is not one this release accepts"""


def install_module_bundle(
    zip_path: Path,
    extract_dir: Path,
    *,
    accepted_digests: Collection[str] | None = ACCEPTED_DIGESTS,
) -> None:
    """Extracts ``zip_path`` and makes the packages in it importable.

    ``accepted_digests=None`` skips the check of the zip's SHA-256.
    """
    if accepted_digests is not None:
        _raise_if_unexpected(zip_path, accepted_digests)
    extract_module_bundle(zip_path, extract_dir)
    import_module_bundle(extract_dir)


def extract_module_bundle(zip_path: Path, extract_dir: Path) -> None:
    """Extracts ``zip_path`` into ``extract_dir``, refusing packages found elsewhere."""
    with zipfile.ZipFile(zip_path) as zf:
        top_level = {PurePosixPath(name).parts[0].split(".")[0] for name in zf.namelist()}
        for name in filter(str.isidentifier, top_level):
            _raise_if_shadowed(name, extract_dir)
        # Files left by an earlier extraction would be imported with the bundle
        shutil.rmtree(extract_dir, ignore_errors=True)
        # extractall() keeps every member inside extract_dir
        zf.extractall(extract_dir)


def import_module_bundle(extract_dir: Path) -> None:
    """Makes the packages extracted by ``extract_module_bundle`` importable."""
    if str(extract_dir) not in sys.path:
        sys.path.append(str(extract_dir))
    for module in pkgutil.iter_modules([str(extract_dir)]):
        if module.ispkg and module.name not in _PACKAGES:
            _PACKAGES.append(module.name)


def module_bundle_packages() -> list[str]:
    """The top-level packages that ``import_module_bundle`` made importable."""
    return list(_PACKAGES)


def _raise_if_unexpected(zip_path: Path, accepted_digests: Collection[str]) -> None:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if digest not in accepted_digests:
        msg = (
            f"This ET release expects a different module bundle than {zip_path} "
            f"(SHA-256 {digest}). Upgrade ET, or delete the bundle and download it again"
        )
        raise UnexpectedModuleBundleError(msg)


def _raise_if_shadowed(name: str, extract_dir: Path) -> None:
    # The bundle's directory is last on sys.path, so a package of the same name
    # anywhere else on it is imported instead.
    other_dirs = [p for p in sys.path if p != str(extract_dir)]
    spec = importlib.machinery.PathFinder.find_spec(name, other_dirs)
    if spec is not None:
        msg = (
            f"{spec.origin or spec.submodule_search_locations} would shadow {name!r} "
            "from the bundle. Remove it and install the bundle again"
        )
        raise ValueError(msg)
