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
from datetime import datetime
from pathlib import Path, PurePosixPath


# SHA-256 of the algo bundle zips that this release accepts
ACCEPTED_DIGESTS: frozenset[str] = frozenset(
    {"6e3e10b05d92c782b31bd04345b13096c3a437eaee929042a5bf294a41c9bd66"}
)

_PACKAGES: list[str] = []


class UnexpectedAlgoBundleError(ValueError):
    """The algo bundle's SHA-256 is not one this release accepts"""

    def __init__(self, zip_path: Path, digest: str) -> None:
        super().__init__(f"This ET release expects a different algo bundle than {zip_path}")
        self.zip_path = zip_path
        self.digest = digest


def install_algo_bundle(
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
    extract_algo_bundle(zip_path, extract_dir)
    import_algo_bundle(extract_dir)


def extract_algo_bundle(zip_path: Path, extract_dir: Path) -> None:
    """Extracts ``zip_path`` into ``extract_dir``, refusing packages found elsewhere."""
    with zipfile.ZipFile(zip_path) as zf:
        top_level = {PurePosixPath(name).parts[0].split(".")[0] for name in zf.namelist()}
        for name in filter(str.isidentifier, top_level):
            _raise_if_shadowed(name, extract_dir)
        # Files left by an earlier extraction would be imported with the bundle
        shutil.rmtree(extract_dir, ignore_errors=True)
        # extractall() keeps every member inside extract_dir
        zf.extractall(extract_dir)


def import_algo_bundle(extract_dir: Path) -> None:
    """Makes the packages extracted by ``extract_algo_bundle`` importable."""
    if str(extract_dir) not in sys.path:
        sys.path.append(str(extract_dir))
    for module in pkgutil.iter_modules([str(extract_dir)]):
        if module.ispkg and module.name not in _PACKAGES:
            _PACKAGES.append(module.name)


def algo_bundle_packages() -> list[str]:
    """The top-level packages that ``import_algo_bundle`` made importable."""
    return list(_PACKAGES)


def algo_bundle_digest(zip_path: Path) -> str:
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


def algo_bundle_modified(zip_path: Path) -> str:
    """When ``zip_path`` was last written, as local time"""
    return datetime.fromtimestamp(zip_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def describe_algo_bundle(zip_path: Path) -> str:
    """Tells builds of the algo bundle apart, which no metadata in the zip does"""
    digest = algo_bundle_digest(zip_path)
    return f"{zip_path} (modified {algo_bundle_modified(zip_path)}, SHA-256 {digest[:12]})"


def _raise_if_unexpected(zip_path: Path, accepted_digests: Collection[str]) -> None:
    digest = algo_bundle_digest(zip_path)
    if digest not in accepted_digests:
        raise UnexpectedAlgoBundleError(zip_path, digest)


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
