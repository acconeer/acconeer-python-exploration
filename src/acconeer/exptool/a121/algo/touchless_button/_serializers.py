# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import h5py
import numpy as np

from ._processor import ProcessorResult


S = t.TypeVar("S")
T = t.TypeVar("T")

_ALL_RESULT_FIELDS = (
    "detection_close",
    "detection_far",
)


class PhonyNoneSeries:
    def __next__(self) -> None:
        return None

    def __iter__(self) -> PhonyNoneSeries:
        return self


class ProcessorResultListH5Serializer:
    """
    Reads or writes a touchless button ProcessorResult from/to a given h5py.Group
    """

    # None is not allowed in H5 dataset
    _TRANSLATION_TABLE_BOOL_INT = {
        None: 0,
        True: 1,
        False: 2,
    }

    _TRANSLATION_TABLE_INT_BOOL = {
        0: None,
        1: True,
        2: False,
    }

    def __init__(
        self,
        group: h5py.Group,
        fields: t.Sequence[str] = _ALL_RESULT_FIELDS,
        allow_missing_fields: bool = False,
    ) -> None:
        """
        :param destination: The H5 group that will have datasets read/written to it
        :param fields: The fields to serialize. Has no effect on de-serialization
        :param allow_missing_fields:
            Whether it's acceptable to break type safety during de-serialization
            by replacing missing fields by ``None``. Has no effect on serialization.
        """
        self.group = group
        self.fields = fields
        self.allow_missing_fields = allow_missing_fields

    def serialize(self, results: t.List[ProcessorResult]) -> None:

        if "detection_close" in self.fields:
            self.group.create_dataset(
                "detection_close",
                dtype=int,
                data=np.array(
                    [self._TRANSLATION_TABLE_BOOL_INT[res.detection_close] for res in results]
                ),
                track_times=False,
            )

        if "detection_far" in self.fields:
            self.group.create_dataset(
                "detection_far",
                dtype=int,
                data=np.array(
                    [self._TRANSLATION_TABLE_BOOL_INT[res.detection_far] for res in results]
                ),
                track_times=False,
            )

    def deserialize(self, _: None) -> t.List[ProcessorResult]:

        groups = (
            self.group.get("detection_close", PhonyNoneSeries()),
            self.group.get("detection_far", PhonyNoneSeries()),
        )

        if all(isinstance(group, PhonyNoneSeries) for group in groups):
            return []

        return [
            ProcessorResult(
                detection_close=self._TRANSLATION_TABLE_INT_BOOL[detection_close],
                detection_far=self._TRANSLATION_TABLE_INT_BOOL[detection_far],
            )
            for (
                detection_close,
                detection_far,
            ) in zip(*groups)
        ]
