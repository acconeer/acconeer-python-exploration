# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from enum import Enum, unique
from typing import Optional, Type, TypeVar


T = TypeVar("T", bound=Enum)


def find_by_value(enum: Type[T], value: object) -> Optional[T]:
    for member in enum:
        if member.value == value:
            return member
    return None


def find_by_first_element_in_value(enum: Type[T], value: object) -> Optional[T]:
    for member in enum:
        if member.value[0] == value:
            return member
    return None


def find_by_name(enum: Type[T], name: object) -> Optional[T]:
    for member in enum:
        if member.name == name:
            return member
    return None


def find_by_lowercase_name(enum: Type[T], lowercase_name: object) -> Optional[T]:
    for member in enum:
        if member.name.lower() == lowercase_name:
            return member
    return None


@unique
class Profile(Enum):
    """Profile"""

    PROFILE_1 = 1
    PROFILE_2 = 2
    PROFILE_3 = 3
    PROFILE_4 = 4
    PROFILE_5 = 5

    @classmethod
    def _missing_(cls, value: object) -> Optional[Profile]:
        return find_by_value(cls, value) or find_by_name(cls, value)


@unique
class PRF(Enum):
    """Pulse Repetition Frequency (PRF)

    Pulse Repetition Frequency, PRF, is the frequency at which pulses are sent out from
    the radar system. The measurement time is approximately proportional to the PRF.
    The higher the PRF, the shorter the measurement time.

    This parameter sets the Maximum Measurable Distance, MMD, that can be achieved. MMD is the
    maximum value for the end point, i.e., the start point + (number of points * step length).
    For example, an MMD of 7.0 m means that the range cannot be set further out than 7.0 m.

    It also sets the Maximum Unambiguous Range, MUR, that can be achieved. MUR is the maximum
    distance at which an object can be located to guarantee that its reflection corresponds to
    the most recent transmitted pulse. Objects farther away than the MUR may fold into the
    measured range. For example, with a MUR of 11.5 m, an object at 13.5 m could become
    visible at 2 m.

    ================= ======== ====== ======
    PRF Setting            PRF    MMD    MUR
    ================= ======== ====== ======
    PRF_19_5_MHZ [*]_ 19.5 MHz  3.1 m  7.7 m
    PRF_15_6_MHZ      15.6 MHz  5.1 m  9.6 m
    PRF_13_0_MHZ      13.0 MHz  7.0 m 11.5 m
    PRF_8_7_MHZ        8.7 MHz 12.7 m 17.3 m
    PRF_6_5_MHZ        6.5 MHz 18.5 m 23.1 m
    PRF_5_2_MHZ        5.2 MHz 24.3 m 28.8 m
    ================= ======== ====== ======

    .. [*] 19.5MHz is only available for profile 1.
    """

    #               PRF       MMD  MUR
    PRF_19_5_MHz = (19500000, 3.1, 7.7)
    PRF_15_6_MHz = (15600000, 5.1, 9.6)
    PRF_13_0_MHz = (13000000, 7.0, 11.5)
    PRF_8_7_MHz = (8700000, 12.7, 17.3)
    PRF_6_5_MHz = (6500000, 18.5, 23.1)
    PRF_5_2_MHz = (5200000, 24.3, 28.8)

    @property
    def frequency(self) -> int:
        return int(self.value[0])

    @property
    def maximum_measurable_distance(self) -> float:
        return float(self.value[1])

    @property
    def mmd(self) -> float:
        return self.maximum_measurable_distance

    @property
    def maximum_unambiguous_range(self) -> float:
        return float(self.value[2])

    @property
    def mur(self) -> float:
        return self.maximum_unambiguous_range

    @classmethod
    def _missing_(cls, value: object) -> Optional[PRF]:
        return find_by_first_element_in_value(cls, value) or find_by_name(cls, value)


@unique
class IdleState(Enum):
    """Idle state"""

    DEEP_SLEEP = 0
    SLEEP = 1
    READY = 2

    @classmethod
    def _missing_(cls, value: object) -> Optional[IdleState]:
        if find_by_value(cls, value) is not None:
            return find_by_value(cls, value)

        if find_by_name(cls, value) is not None:
            return find_by_name(cls, value)

        if find_by_lowercase_name(cls, value) is not None:
            return find_by_lowercase_name(cls, value)

        return None

    def is_deeper_than(self, other: IdleState) -> bool:
        return self.value < other.value
