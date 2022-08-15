# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from pathlib import Path
from typing import Optional

import attrs
import h5py

from acconeer.exptool.app.new._enums import PluginGeneration


@attrs.frozen(kw_only=True)
class FileFindings:
    generation: PluginGeneration
    key: Optional[str]


def investigate_file(path: Path) -> Optional[FileFindings]:
    if path.suffix != ".h5":
        return None

    try:
        f = h5py.File(path, "r")
    except Exception:
        return None

    try:
        try:
            generation = PluginGeneration(bytes(f["generation"][()]).decode())
        except Exception:
            return None

        try:
            key = bytes(f["algo"]["key"][()]).decode()
        except KeyError:
            key = None
    finally:
        f.close()

    if generation != PluginGeneration.A121:
        return None

    return FileFindings(
        generation=generation,
        key=key,
    )
