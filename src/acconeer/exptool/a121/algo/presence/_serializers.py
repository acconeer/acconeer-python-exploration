# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import typing as t

import h5py
import numpy as np

from ._processors import ProcessorResult


S = t.TypeVar("S")
T = t.TypeVar("T")

_ALL_RESULT_FIELDS: t.Final = (
    "intra_presence_score",
    "inter_presence_score",
    "presence_distance",
    "presence_detected",
    # "extra_result" ignored by default
)


class PhonyNoneSeries:
    def __next__(self) -> None:
        return None

    def __iter__(self) -> PhonyNoneSeries:
        return self


class ProcessorResultListH5Serializer:
    """
    Reads or writes a presence ProcessorResult from/to a given h5py.Group
    """

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
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "intra_presence_score" in self.fields:
            self.group.create_dataset(
                "intra_presence_score",
                dtype=float,
                data=np.array([res.intra_presence_score for res in results]),
                track_times=False,
            )

        if "inter_presence_score" in self.fields:
            self.group.create_dataset(
                "inter_presence_score",
                dtype=float,
                data=np.array([res.inter_presence_score for res in results]),
                track_times=False,
            )

        if "presence_distance" in self.fields:
            self.group.create_dataset(
                "presence_distance",
                dtype=float,
                data=np.array([res.presence_distance for res in results]),
                track_times=False,
            )

        if "presence_detected" in self.fields:
            self.group.create_dataset(
                "presence_detected",
                dtype=bool,
                data=np.array([res.presence_detected for res in results]),
                track_times=False,
            )

    def deserialize(self, _: None) -> t.List[ProcessorResult]:
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        groups = (
            self.group.get("intra_presence_score", PhonyNoneSeries()),
            self.group.get("inter_presence_score", PhonyNoneSeries()),
            self.group.get("presence_distance", PhonyNoneSeries()),
            self.group.get("presence_detected", PhonyNoneSeries()),
        )

        if all(isinstance(group, PhonyNoneSeries) for group in groups):
            return []

        return [
            ProcessorResult(
                intra_presence_score=intra,
                inter_presence_score=inter,
                presence_distance=distance,
                presence_detected=detected,
                extra_result=None,  # type: ignore[arg-type]
            )
            for intra, inter, distance, detected in zip(*groups)
        ]
