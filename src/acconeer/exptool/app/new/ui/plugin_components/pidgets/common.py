# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t


_T = t.TypeVar("_T")
MaybeIterable = t.Union[_T, t.Iterable[_T]]


def as_sequence(a: MaybeIterable[_T]) -> t.Sequence[_T]:
    """
    Converts a single element or a iterable to a sequence

    Examples:

    >>> as_sequence('a')
    ('a',)

    >>> as_sequence(['a', 'b'])
    ('a', 'b')
    """
    if isinstance(a, t.Iterable):
        return tuple(a)
    else:
        return (a,)
