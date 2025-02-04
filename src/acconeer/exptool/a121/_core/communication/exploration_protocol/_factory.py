# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

from typing import Optional, Type

from packaging.version import Version

from ._latest import ExplorationProtocol, ExplorationProtocolError
from ._no_5_2_mhz import ExplorationProtocol_No_5_2MHz_PRF
from ._no_15_6_mhz import ExplorationProtocol_No_15_6MHz_PRF
from ._no_calibration_reuse import ExplorationProtocol_NoCalibrationReuse
from ._no_iq_imb_comp import ExplorationProtocol_No_IQ_Imb_Comp


def get_exploration_protocol(rss_version: Optional[Version] = None) -> Type[ExplorationProtocol]:
    if rss_version is None:
        return ExplorationProtocol

    if rss_version <= Version("0.2.0"):
        msg = "Unsupported RSS version"
        raise ExplorationProtocolError(msg)

    if rss_version < Version("0.4.3.dev280"):
        return ExplorationProtocol_NoCalibrationReuse

    if rss_version < Version("0.4.3.dev310"):
        return ExplorationProtocol_No_5_2MHz_PRF

    if rss_version < Version("0.7.1.dev37"):
        return ExplorationProtocol_No_15_6MHz_PRF

    if rss_version < Version("1.9.1.dev84"):
        return ExplorationProtocol_No_IQ_Imb_Comp

    return ExplorationProtocol
