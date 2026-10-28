# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

import hashlib
import importlib
import sys
import zipfile
from enum import Enum, auto
from pathlib import Path

import pytest

from acconeer.exptool._artifact_repository import (
    UnexpectedAlgoBundleError,
    _algo_bundle,
    install_algo_bundle,
)
from acconeer.exptool.a2.algo._plugin_specs.presence_tracking_wall_mount import (
    PRESENCE_TRACKING_WALL_MOUNT_PLUGIN,
)
from acconeer.exptool.app.new import PluginFamily, PluginGeneration, PluginPresetBase
from acconeer.exptool.app.new.pluginbase import BundledPluginSpec


_PACKAGE = "acconeer.algo_bundle"
_PACKAGE_DIR = "acconeer/algo_bundle"


@pytest.fixture(autouse=True)
def _restore_import_state(monkeypatch: pytest.MonkeyPatch, algo_bundle_extract_dir: Path | None):
    # The bundle installed by --algo-bundle holds the package these tests fake
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != str(algo_bundle_extract_dir)])
    for name in [n for n in sys.modules if n == _PACKAGE or n.startswith(f"{_PACKAGE}.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.delattr(sys.modules["acconeer"], "algo_bundle", raising=False)
    monkeypatch.setattr(_algo_bundle, "_PACKAGES", [])
    modules_before = set(sys.modules)
    yield
    for name in set(sys.modules) - modules_before:
        del sys.modules[name]


def _write_zip(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for filename, content in members.items():
            zf.writestr(filename, content)
    return path


def _test__install_algo_bundle(zip_path: Path, extract_dir: Path) -> None:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    install_algo_bundle(zip_path, extract_dir, accepted_digests={digest})


def test_bundle_of_an_unexpected_digest_is_refused(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": ""})

    with pytest.raises(UnexpectedAlgoBundleError):
        install_algo_bundle(zip_path, tmp_path / "extracted", accepted_digests={"0" * 64})

    assert not (tmp_path / "extracted").exists()


def test_bundle_is_checked_against_the_digests_of_this_release(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": ""})

    with pytest.raises(ValueError, match="expects a different algo bundle"):
        install_algo_bundle(zip_path, tmp_path / "extracted")


def test_installed_package_is_importable(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip",
        {f"{_PACKAGE_DIR}/__init__.py": "", f"{_PACKAGE_DIR}/module.py": "name = 'bundled'"},
    )

    _test__install_algo_bundle(zip_path, tmp_path / "extracted")

    assert importlib.import_module(f"{_PACKAGE}.module").name == "bundled"


def test_bundle_without_the_algo_bundle_package_is_refused(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {"other_package/__init__.py": ""})

    with pytest.raises(ValueError, match=f"no package {_PACKAGE}"):
        _test__install_algo_bundle(zip_path, tmp_path / "extracted")


def test_installing_again_adds_the_directory_once(tmp_path: Path) -> None:
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": ""})

    _test__install_algo_bundle(zip_path, tmp_path / "extracted")
    _test__install_algo_bundle(zip_path, tmp_path / "extracted")

    assert sys.path.count(str(tmp_path / "extracted")) == 1


def test_install_leaves_no_stale_files_behind(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extracted"
    (extract_dir / "stale_package").mkdir(parents=True)
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": ""})

    _test__install_algo_bundle(zip_path, extract_dir)

    assert not (extract_dir / "stale_package").exists()


def test_keeps_members_inside_its_directory(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": "", "../evil.py": ""}
    )

    _test__install_algo_bundle(zip_path, tmp_path / "extracted")

    assert not (tmp_path / "evil.py").exists()


def test_rejects_package_shadowed_by_one_on_the_path(tmp_path: Path) -> None:
    shadowing_dir = tmp_path / "shadowing"
    (shadowing_dir / _PACKAGE_DIR).mkdir(parents=True)
    (shadowing_dir / _PACKAGE_DIR / "__init__.py").write_text("")
    sys.path.insert(0, str(shadowing_dir))
    zip_path = _write_zip(tmp_path / "bundle.zip", {f"{_PACKAGE_DIR}/__init__.py": ""})

    with pytest.raises(ValueError, match=f"shadow {_PACKAGE!r}"):
        _test__install_algo_bundle(zip_path, tmp_path / "extracted")


def test_rejects_bundle_whose_acconeer_is_no_namespace(tmp_path: Path) -> None:
    zip_path = _write_zip(
        tmp_path / "bundle.zip",
        {"acconeer/__init__.py": "", f"{_PACKAGE_DIR}/__init__.py": ""},
    )

    with pytest.raises(ValueError, match="shadow 'acconeer'"):
        _test__install_algo_bundle(zip_path, tmp_path / "extracted")


def test_presence_tracking_wall_mount_needs_the_algo_bundle() -> None:
    assert PRESENCE_TRACKING_WALL_MOUNT_PLUGIN.requires_algo_bundle_artifact


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
            f"{_PACKAGE_DIR}/__init__.py": "",
            f"{_PACKAGE_DIR}/plugin_specs.py": _BUNDLED_SPEC_MODULE,
            # Sorts first, so the lookup passes it before finding the spec
            "a_package_without_plugins/__init__.py": "",
        },
    )
    _test__install_algo_bundle(zip_path, tmp_path / "extracted")


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
