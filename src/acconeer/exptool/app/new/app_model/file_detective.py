# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

from pathlib import Path

import attrs
import h5py
from packaging.version import Version

from acconeer.exptool.app.new._enums import PluginGeneration
from acconeer.exptool.app.new._exceptions import HandledException


@attrs.frozen(kw_only=True)
class FileFindings:
    generation: PluginGeneration
    key: str | None
    et_version: Version | None


def investigate_file(path: Path) -> FileFindings:
    if path.suffix != ".h5":
        msg = f"Cannot load {path.name}: only .h5 recordings can be loaded"
        raise HandledException(msg)

    try:
        f = h5py.File(path, "r")
    except Exception as e:
        msg = f"Cannot read {path.name}: {e}"
        raise HandledException(msg) from e

    try:
        try:
            generation = _a111_or_named_generation(f)
        except Exception as e:
            msg = (
                f"Cannot load {path.name}: it is not an Exploration Tool recording, "
                "as it names no known sensor generation"
            )
            raise HandledException(msg) from e

        try:
            key = bytes(f["algo"]["key"][()]).decode()
        except KeyError:
            key = None

        try:
            et_version = Version(bytes(f["lib_version"][()]).decode())
        except KeyError:
            et_version = None
    finally:
        f.close()

    return FileFindings(
        generation=generation,
        key=key,
        et_version=et_version,
    )


def _a111_or_named_generation(f: h5py.File) -> PluginGeneration:
    if "generation" not in f and "mode" in f and "data_info" in f:
        return PluginGeneration.A111

    return PluginGeneration(bytes(f["generation"][()]).decode())
