from __future__ import annotations

import warnings

from acconeer.exptool.a121._core.entities import SessionConfig
from acconeer.exptool.a121._core.utils import map_over_extended_structure

from ._latest import ExplorationProtocol


class ExplorationProtocol_0_2_0(ExplorationProtocol):
    @classmethod
    def _setup_command_preprocessing(cls, session_config: SessionConfig) -> dict:
        command_dict = super()._setup_command_preprocessing(session_config)
        command_dict["groups"] = map_over_extended_structure(
            cls.__adapt_entry, command_dict["groups"]
        )
        return command_dict

    @classmethod
    def __adapt_entry(cls, entry: dict) -> dict:
        if entry["double_buffering"]:
            warnings.warn("Double buffering is not supported and will not be used")

        del entry["double_buffering"]
        return entry
