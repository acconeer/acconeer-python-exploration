# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from acconeer.exptool._artifact_repository import (
    ArtifactRepositoryError,
    DevSiteRepository,
    create_artifact_repository,
    get_plugin_manager,
    hookimpl,
    load_plugin_file,
)


@pytest.fixture(autouse=True)
def unregister_test_plugins(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        "acconeer.exptool._artifact_repository._dev_site_repository._load_saved_cookies",
        lambda: None,
    )
    pm = get_plugin_manager()
    plugins_before = pm.get_plugins()
    yield
    for plugin in pm.get_plugins() - plugins_before:
        pm.unregister(plugin)


def test_defaults_to_dev_site() -> None:
    assert isinstance(create_artifact_repository(), DevSiteRepository)


def test_registered_plugin_overrides_dev_site() -> None:
    sentinel = object()

    class _Plugin:
        @hookimpl
        def create_artifact_repository(self) -> object:
            return sentinel

    get_plugin_manager().register(_Plugin())

    assert create_artifact_repository() is sentinel


def test_plugin_returning_none_defers_to_dev_site() -> None:
    class _Plugin:
        @hookimpl
        def create_artifact_repository(self) -> None:
            return None

    get_plugin_manager().register(_Plugin())

    assert isinstance(create_artifact_repository(), DevSiteRepository)


def test_load_plugin_file_overrides_dev_site(tmp_path: Path) -> None:
    plugin_file = tmp_path / "my_plugin.py"
    plugin_file.write_text(
        "from acconeer.exptool._artifact_repository import DevSiteRepository, hookimpl\n"
        "\n"
        "@hookimpl\n"
        "def create_artifact_repository():\n"
        "    return DevSiteRepository(cookies=None, base_url='http://localhost:8000')\n"
    )

    load_plugin_file(plugin_file)
    repository = create_artifact_repository()

    assert isinstance(repository, DevSiteRepository)
    assert repository.base_url == "http://localhost:8000"


def test_load_missing_plugin_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ArtifactRepositoryError, match="Could not load"):
        load_plugin_file(tmp_path / "does_not_exist.py")


def test_load_non_python_plugin_file_raises(tmp_path: Path) -> None:
    plugin_file = tmp_path / "plugin.txt"
    plugin_file.write_text("")

    with pytest.raises(ArtifactRepositoryError, match="not a Python file"):
        load_plugin_file(plugin_file)
