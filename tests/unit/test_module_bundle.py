# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import importlib
import sys
import zipfile
from pathlib import Path

import pytest

from acconeer.exptool._artifact_repository import install_module_bundle


_PACKAGE = "bundled_test_package"


@pytest.fixture(autouse=True)
def _restore_import_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    modules_before = set(sys.modules)
    yield
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]


def _write_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for filename, content in members.items():
            zf.writestr(filename, content)
    return path


def test_installed_package_is_importable(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip",
        {f"{_PACKAGE}/__init__.py": "", f"{_PACKAGE}/module.py": "name = 'bundled'"},
    )

    install_module_bundle(zip_path, tmp_path / "extracted")

    assert importlib.import_module(f"{_PACKAGE}.module").name == "bundled"


def test_installing_again_adds_the_directory_once(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE}/__init__.py": ""})

    install_module_bundle(zip_path, tmp_path / "extracted")
    install_module_bundle(zip_path, tmp_path / "extracted")

    assert sys.path.count(str(tmp_path / "extracted")) == 1


def test_keeps_members_inside_its_directory(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {"../evil.py": ""})

    install_module_bundle(zip_path, tmp_path / "extracted")

    assert not (tmp_path / "evil.py").exists()


def test_rejects_package_shadowed_by_one_on_the_path(tmp_path: Path) -> None:
    shadowing_dir = tmp_path / "shadowing"
    (shadowing_dir / _PACKAGE).mkdir(parents=True)
    (shadowing_dir / _PACKAGE / "__init__.py").write_text("")
    sys.path.insert(0, str(shadowing_dir))
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE}/__init__.py": ""})

    with pytest.raises(ValueError, match="shadow"):
        install_module_bundle(zip_path, tmp_path / "extracted")
