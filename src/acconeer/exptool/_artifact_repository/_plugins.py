# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Pluggy hooks that pick which ``ArtifactRepository`` serves the flash wizard/CLI.

A plugin is a module with a ``create_artifact_repository`` hook implementation.
It is either loaded from a Python file with ``load_plugin_file()``, or comes
from an installed package exposing it under the ``acconeer-exptool`` entry
point group::

    [project.entry-points.acconeer-exptool]
    my_repository = "my_package.my_module"

Plugins registered later are asked first, so any plugin overrides the
built-in developer site repository.
"""

from __future__ import annotations

import functools
import importlib.util
from pathlib import Path

import pluggy

from ._interface import ArtifactRepository, ArtifactRepositoryError


PROJECT_NAME = "acconeer-exptool"

hookspec = pluggy.HookspecMarker(PROJECT_NAME)
hookimpl = pluggy.HookimplMarker(PROJECT_NAME)


class ArtifactRepositoryModuleSpec:
    @hookspec(firstresult=True)
    def create_artifact_repository(self) -> ArtifactRepository | None:
        """Returns the repository to fetch artifacts from.

        Return ``None`` to let the other plugins provide one.
        """
        raise NotImplementedError


@functools.cache
def get_plugin_manager() -> pluggy.PluginManager:
    from . import _dev_site_repository

    pm = pluggy.PluginManager(PROJECT_NAME)
    pm.add_hookspecs(ArtifactRepositoryModuleSpec)
    pm.register(_dev_site_repository)
    pm.load_setuptools_entrypoints(PROJECT_NAME)
    return pm


def load_plugin_file(path: str | Path) -> None:
    """Imports the Python file at ``path`` and registers it as a plugin."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(f"artifact_repository_plugin:{path}", path)
    if spec is None or spec.loader is None:
        msg = f"'{path}' is not a Python file"
        raise ArtifactRepositoryError(msg)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        msg = f"Could not load the artifact repository plugin '{path}': {e}"
        raise ArtifactRepositoryError(msg) from e

    get_plugin_manager().register(module)


def create_artifact_repository() -> ArtifactRepository:
    """Asks the registered plugins for a repository, the latest registered first."""
    repository = get_plugin_manager().hook.create_artifact_repository()
    if repository is None:
        msg = "No artifact repository plugin provided a repository"
        raise ArtifactRepositoryError(msg)

    return repository  # type: ignore[no-any-return]
