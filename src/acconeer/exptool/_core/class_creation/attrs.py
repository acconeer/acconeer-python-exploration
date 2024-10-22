# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import typing as t
from typing import Callable, Optional

import attrs
import numpy as np
from numpy import typing as npt


_S = t.TypeVar("_S")
_T = t.TypeVar("_T")
_U = t.TypeVar("_U")


def ndarray_isclose(a: npt.ArrayLike, b: npt.ArrayLike) -> bool:
    return bool(np.isclose(a, b, equal_nan=True).all())


def _dict_wrapper(f: Callable[[_S, _T], bool]) -> Callable[[dict[_U, _S], dict[_U, _T]], bool]:
    def wrapper(a: dict[_U, _S], b: dict[_U, _T]) -> bool:
        if a.keys() != b.keys():
            return False

        return all(f(a[key], b[key]) for key in a)

    return wrapper


def _optional_wrapper(f: Callable[[_S, _T], bool]) -> Callable[[Optional[_S], Optional[_T]], bool]:
    def wrapper(a: Optional[_S], b: Optional[_T]) -> bool:
        if a is None or b is None:
            return a is b
        else:
            return f(a, b)

    return wrapper


attrs_ndarray_eq = attrs.cmp_using(eq=np.array_equal)
attrs_optional_ndarray_eq = attrs.cmp_using(eq=_optional_wrapper(np.array_equal))
attrs_ndarray_isclose = attrs.cmp_using(eq=ndarray_isclose)
attrs_optional_ndarray_isclose = attrs.cmp_using(eq=_optional_wrapper(ndarray_isclose))
attrs_dict_ndarray_isclose = attrs.cmp_using(eq=_dict_wrapper(ndarray_isclose))


def attrs_ndarray_validator(
    ndim: int, element_type: np.dtype[np.generic]
) -> t.Callable[[t.Any, t.Any, t.Any], None]:
    """
    Creates a validator to be used in attrs fields. Does the following checks:

    1. The new value is a np.ndarray
    2. It has ``ndim`` dimensions
    3. Its elements have the type ``element_type`` (e.g. np.float64, np.int_, etc.)
    """

    def inner(_: t.Any, attribute: attrs.Attribute[t.Any], value: t.Any) -> None:
        if not isinstance(value, np.ndarray):
            msg = f"{attribute.name!r} needs to be a numpy array"
            raise TypeError(msg)

        if value.ndim != ndim:
            raise ValueError(
                f"{attribute.name!r} has {value.ndim} dimensions. "
                + f"It needs to have {ndim} dimensions"
            )

        if value.dtype != element_type:
            msg = f"{attribute.name!r} needs to have dtype {element_type!r}"
            raise ValueError(msg)

    return inner
