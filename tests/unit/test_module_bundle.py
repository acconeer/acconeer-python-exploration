# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import importlib
import sys
import zipfile
from enum import Enum, auto
from pathlib import Path

import pytest

from acconeer.exptool._artifact_repository import _module_bundle, install_module_bundle
from acconeer.exptool.app.new import PluginFamily, PluginGeneration, PluginPresetBase
from acconeer.exptool.app.new.pluginbase import BundledPluginSpec


_PACKAGE = "bundled_test_package"


@pytest.fixture(autouse=True)
def _restore_import_state(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(_module_bundle, "_PACKAGES", [])
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


def test_install_leaves_no_stale_files_behind(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extracted"
    (extract_dir / "stale_package").mkdir(parents=True)
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE}/__init__.py": ""})

    install_module_bundle(zip_path, extract_dir)

    assert not (extract_dir / "stale_package").exists()


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


_BUNDLED_SPEC_MODULE = """
from acconeer.exptool.app.new import PluginSpecBase


class FakeSpec(PluginSpecBase):
    def create_backend_plugin(self, callback, key):
        return f"backend of {self.title}"

    def create_view_plugin(self, app_model):
        return f"view of {self.title}"

    def create_plot_plugin(self, app_model):
        return f"plot of {self.title}"

    @classmethod
    def replay_dialog_get_config(cls, path):
        return f"config from {path}"


PLUGIN_SPECS = {"fake": FakeSpec}
"""


class _PresetId(Enum):
    DEFAULT = auto()


def _bundled_spec(key: str) -> BundledPluginSpec:
    return BundledPluginSpec(
        generation=PluginGeneration.A2,
        key=key,
        title="Fake",
        family=PluginFamily.REF_APP,
        presets=[PluginPresetBase(name="Default", preset_id=_PresetId.DEFAULT)],
        default_preset_id=_PresetId.DEFAULT,
    )


def _install_fake_bundle(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip",
        {
            f"{_PACKAGE}/__init__.py": "",
            f"{_PACKAGE}/plugin_specs.py": _BUNDLED_SPEC_MODULE,
            # Sorts first, so the lookup passes it before finding the spec
            "a_package_without_plugins/__init__.py": "",
        },
    )
    install_module_bundle(zip_path, tmp_path / "extracted")


def test_bundled_plugin_spec_creates_plugins_of_the_bundled_spec(tmp_path: Path) -> None:
    _install_fake_bundle(tmp_path)

    backend_plugin = _bundled_spec("fake").create_backend_plugin(callback=print, key="fake")

    assert backend_plugin == "backend of Fake"


def test_bundled_plugin_spec_reads_replay_config_with_the_bundled_spec(tmp_path: Path) -> None:
    _install_fake_bundle(tmp_path)

    assert _bundled_spec("fake").replay_dialog_get_config(Path("rec.h5")) == "config from rec.h5"


def test_bundled_plugin_spec_missing_from_the_bundle_says_so(tmp_path: Path) -> None:
    _install_fake_bundle(tmp_path)

    with pytest.raises(ValueError, match="no plugin 'missing'"):
        _bundled_spec("missing").create_backend_plugin(callback=print, key="missing")
