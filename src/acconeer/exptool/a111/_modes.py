# Copyright (c) Acconeer AB, 2022
# All rights reserved

import enum


class Mode(enum.Enum):
    POWER_BINS = "power_bins"
    ENVELOPE = "envelope"
    IQ = "iq"
    SPARSE = "sparse"


def get_mode(mode):
    if mode is None:
        return None

    if isinstance(mode, Mode):
        return mode

    if isinstance(mode, str):
        try:
            return Mode(mode.strip().lower())
        except ValueError:
            pass

        try:
            return Mode.__members__[mode.strip().upper()]
        except KeyError:
            pass

    raise ValueError("unknown mode")
