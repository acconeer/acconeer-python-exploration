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
        return Mode(mode.strip().lower())

    raise ValueError("unknown mode")
