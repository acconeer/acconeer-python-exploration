# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import abc
import typing as t

import h5py
import typing_extensions as te

from acconeer.exptool import a121


T = t.TypeVar("T")
S = t.TypeVar("S")

AlgorithmResult = t.Any


class Algorithm(te.Protocol):
    def process(self, result: a121.Result) -> AlgorithmResult:
        ...


class ResultSerializer(abc.ABC, t.Generic[S, T]):
    def serialize(self, result: S) -> T:
        ...

    def deserialize(self, result: T) -> S:
        ...


class H5ResultSerializer(ResultSerializer[S, None]):
    def __init__(self, group: h5py.Group) -> None:
        ...


AlgorithmFactory = t.Callable[[a121.H5Record], Algorithm]
