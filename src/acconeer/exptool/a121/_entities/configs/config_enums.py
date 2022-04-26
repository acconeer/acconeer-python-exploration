from __future__ import annotations

from enum import Enum, IntEnum, unique
from typing import Optional, Type, TypeVar


T = TypeVar("T", bound=Enum)


def search_enum_after_value(enum: Type[T], value: object) -> Optional[T]:
    for member in enum:
        if member.name == value or member.value == value:
            return member
    return None


@unique
class Profile(IntEnum):
    PROFILE_1 = 1
    PROFILE_2 = 2
    PROFILE_3 = 3
    PROFILE_4 = 4
    PROFILE_5 = 5

    @classmethod
    def _missing_(cls, value: object) -> Optional[Profile]:
        return search_enum_after_value(cls, value)


@unique
class PRF(IntEnum):
    PRF_19_5_MHz = 19500000
    PRF_13_0_MHz = 13000000
    PRF_8_7_MHz = 8700000
    PRF_6_5_MHz = 6500000

    @property
    def frequency(self) -> int:
        return self.value

    @classmethod
    def _missing_(cls, value: object) -> Optional[PRF]:
        return search_enum_after_value(cls, value)
