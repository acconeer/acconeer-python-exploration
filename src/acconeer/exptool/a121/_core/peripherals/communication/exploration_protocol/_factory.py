from __future__ import annotations

from typing import Optional, Type

from packaging.version import Version

from ._latest import ExplorationProtocol, ExplorationProtocolError
from ._v0_2_0 import ExplorationProtocol_0_2_0


def get_exploration_protocol(rss_version: Optional[Version] = None) -> Type[ExplorationProtocol]:
    if rss_version is None:
        return ExplorationProtocol

    if rss_version <= Version("0.1.0"):
        raise ExplorationProtocolError("Unsupported RSS version")

    if rss_version <= Version("0.2.0"):
        return ExplorationProtocol_0_2_0

    return ExplorationProtocol