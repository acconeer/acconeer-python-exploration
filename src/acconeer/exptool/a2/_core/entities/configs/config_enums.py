# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto, unique

import typing_extensions as te

from acconeer.exptool._core.class_creation.enum import (
    find_by_lowercase_name,
    find_by_name,
    find_by_value,
)


@unique
class Profile(Enum):
    """Profile"""

    PROFILE_1 = 1
    PROFILE_2 = 2
    PROFILE_3 = 3
    PROFILE_4 = 4
    PROFILE_5 = 5
    PROFILE_6 = 6
    PROFILE_7 = 7

    @classmethod
    def _missing_(cls, value: object) -> te.Self | None:
        return find_by_value(cls, value) or find_by_name(cls, value)

    def __int__(self) -> int:
        return self.value


class PRF(Enum):
    """
    Pulse Repetition Frequency

    Pulse Repetition Frequency, PRF, is the frequency at
    which pulses are sent out from the radar system. The
    measurement time is approximately proportional to the
    PRF. The higher the PRF, the shorter the measurement time.

    This parameter sets the Maximum Measurable Distance, MMD,
    that can be achieved. MMD is the maximum value for the end point,
    i.e.,the start point + (number of points * step length).
    For example, an MMD of 7.0 m means that the range cannot
    be set further out than 7.0 m.

    It also sets the Maximum Unambiguous Range, MUR, that can be achieved.
    MUR is the maximum distance at which an object can be located to guarantee
    that its reflection corresponds to the most recent transmitted pulse.
    Objects farther away than the MUR may fold into the measured range.
    For example, with a MUR of 11.5 m, an object at 13.5 m could become
    visible at 2 m.

    ================= ======== ====== ======
    PRF Setting            PRF    MMD    MUR
    ================= ======== ====== ======
    PRF_5_3_MHZ        5.3 MHz 25.0 m 28.0 m
    PRF_8_3_MHZ        8.3 MHz 15.0 m 18.0 m
    PRF_12_5_MHZ      12.5 MHz  9.0 m 12.0 m
    PRF_15_8_MHZ      15.8 MHz  6.6 m  9.6 m
    PRF_20_8_MHZ      20.8 MHz  4.2 m  7.2 m
    PRF_27_7_MHZ      27.7 MHz  2.4 m  5.4 m
    ================= ======== ====== ======

    """

    PRF_5_3_MHZ = auto()
    PRF_8_3_MHZ = auto()
    PRF_12_5_MHZ = auto()
    PRF_15_8_MHZ = auto()
    PRF_20_8_MHZ = auto()
    PRF_27_7_MHZ = auto()

    @classmethod
    def _missing_(cls, value: object) -> te.Self | None:
        return find_by_name(cls, value)

    @property
    def frequency(self) -> int:
        """Pulse repetition frequency in Hz"""
        return _PRF_FREQUENCY_HZ[self.name]


_PRF_FREQUENCY_HZ = {
    "PRF_5_3_MHZ": 5_300_000,
    "PRF_8_3_MHZ": 8_300_000,
    "PRF_12_5_MHZ": 12_500_000,
    "PRF_15_8_MHZ": 15_800_000,
    "PRF_20_8_MHZ": 20_800_000,
    "PRF_27_7_MHZ": 27_700_000,
}


@unique
class IdleState(Enum):
    """Idle state"""

    READY = 0
    ARMED = 1

    @classmethod
    def _missing_(cls, value: object) -> IdleState | None:
        if find_by_value(cls, value) is not None:
            return find_by_value(cls, value)

        if find_by_name(cls, value) is not None:
            return find_by_name(cls, value)

        if find_by_lowercase_name(cls, value) is not None:
            return find_by_lowercase_name(cls, value)

        return None
