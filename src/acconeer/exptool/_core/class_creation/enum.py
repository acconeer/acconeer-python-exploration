# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t
from enum import Enum


_EnumT = t.TypeVar("_EnumT", bound=Enum)


def find_by_value(enum: type[_EnumT], value: object) -> t.Optional[_EnumT]:
    """Helper for writing readable Enum._missing_ methods"""
    for member in enum:
        if member.value == value:
            return member
    return None


def find_by_first_element_in_value(enum: type[_EnumT], value: object) -> t.Optional[_EnumT]:
    """Helper for writing readable Enum._missing_ methods"""
    for member in enum:
        if member.value[0] == value:
            return member
    return None


def find_by_name(enum: type[_EnumT], name: object) -> t.Optional[_EnumT]:
    """Helper for writing readable Enum._missing_ methods"""
    for member in enum:
        if member.name == name:
            return member
    return None


def find_by_lowercase_name(enum: type[_EnumT], lowercase_name: object) -> t.Optional[_EnumT]:
    """Helper for writing readable Enum._missing_ methods"""
    for member in enum:
        if member.name.lower() == lowercase_name:
            return member
    return None
