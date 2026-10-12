# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import importlib
import sys
import zipfile
from pathlib import Path, PurePosixPath

import pytest

from acconeer.exptool._artifact_repository import install_module_bundle
from acconeer.exptool._artifact_repository._module_bundle import _PARENT_BY_MODULE


_MEMBER = "presence/bundled_module"
_PARENT = "acconeer.exptool.a121.algo.presence"


@pytest.fixture(autouse=True)
def _restore_import_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(_PARENT_BY_MODULE, _MEMBER, _PARENT)
    for parent in set(_PARENT_BY_MODULE.values()):
        pkg = importlib.import_module(parent)
        monkeypatch.setattr(pkg, "__path__", list(pkg.__path__))
    modules_before = set(sys.modules)
    yield
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]


def _write_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for filename, content in members.items():
            zf.writestr(filename, content)
    return path


def test_every_parent_is_an_importable_package() -> None:
    for parent in set(_PARENT_BY_MODULE.values()):
        assert hasattr(importlib.import_module(parent), "__path__"), parent


def test_imports_each_module_under_its_package(tmp_path: Path) -> None:
    members = {f"{member}.py": f"name = {member!r}" for member in _PARENT_BY_MODULE}
    zip_path = _write_zip(tmp_path / "bundle.zip", members)

    install_module_bundle(zip_path, tmp_path / "extracted")

    for member, parent in _PARENT_BY_MODULE.items():
        imported = importlib.import_module(f"{parent}.{PurePosixPath(member).name}")
        assert imported.name == member


def test_skips_unknown_module(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_MEMBER}.py": "", "not_a_module.py": ""})

    with pytest.warns(UserWarning, match="not a known module"):
        install_module_bundle(zip_path, tmp_path / "extracted")

    assert not list(tmp_path.rglob("not_a_module.py"))


def test_skips_known_module_in_another_directory(tmp_path: Path) -> None:
    name = PurePosixPath(_MEMBER).name
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_MEMBER}.py": "", f"other/{name}.py": ""})

    with pytest.warns(UserWarning, match=f"'other/{name}.py' is not a known module"):
        install_module_bundle(zip_path, tmp_path / "extracted")


def test_skips_member_escaping_its_directory(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip", {f"{_MEMBER}.py": "", f"{_MEMBER}.py/../../evil.py": ""}
    )

    with pytest.warns(UserWarning, match="not a known module"):
        install_module_bundle(zip_path, tmp_path / "extracted")

    assert not list(tmp_path.rglob("evil.py"))


def test_rejects_module_shadowed_by_existing_file(tmp_path: Path) -> None:
    shadowing_dir = tmp_path / "shadowing"
    shadowing_dir.mkdir()
    (shadowing_dir / f"{PurePosixPath(_MEMBER).name}.py").write_text("")
    importlib.import_module(_PARENT).__path__.insert(0, str(shadowing_dir))
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_MEMBER}.so": ""})

    with pytest.raises(ValueError, match="shadow"):
        install_module_bundle(zip_path, tmp_path / "extracted")
