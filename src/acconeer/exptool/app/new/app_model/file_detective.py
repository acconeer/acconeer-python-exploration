from __future__ import annotations

from pathlib import Path
from typing import Optional

import attrs
import h5py

from .plugin_enums import PluginGeneration


@attrs.frozen(kw_only=True)
class FileFindings:
    generation: PluginGeneration
    key: Optional[str]


def investigate_file(path: Path) -> Optional[FileFindings]:
    if path.suffix != ".h5":
        return None

    with h5py.File(path, "r") as f:
        try:
            generation = PluginGeneration(bytes(f["generation"][()]).decode())
        except Exception:
            return None

        try:
            key = bytes(f["algo"]["key"][()]).decode()
        except KeyError:
            key = None

    if generation != PluginGeneration.A121:
        return None

    return FileFindings(
        generation=generation,
        key=key,
    )
