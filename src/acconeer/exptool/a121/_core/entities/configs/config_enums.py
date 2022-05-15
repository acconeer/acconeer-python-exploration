from __future__ import annotations

from enum import Enum, IntEnum, unique
from typing import Optional, Type, TypeVar


T = TypeVar("T", bound=Enum)


def find_by_value(enum: Type[T], value: object) -> Optional[T]:
    for member in enum:
        if member.value == value:
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
class Profile(IntEnum):
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
class PRF(IntEnum):
    """Pulse Repetition Frequency (PRF)"""

    PRF_19_5_MHz = 19500000
    PRF_13_0_MHz = 13000000
    PRF_8_7_MHz = 8700000
    PRF_6_5_MHz = 6500000

    @property
    def frequency(self) -> int:
        return self.value

    @classmethod
    def _missing_(cls, value: object) -> Optional[PRF]:
        return find_by_value(cls, value) or find_by_name(cls, value)


@unique
class IdleState(IntEnum):
    """Idle state

    Idle state ``DEEP_SLEEP`` is the deepest state where as much of the
    sensor hardware as possible is shut down and idle state ``READY`` is
    the lightest state where most of the sensor hardware is kept on.

    ``DEEP_SLEEP`` is the slowest to transition from while ``READY`` is
    the fastest.
    """

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
        return self < other
