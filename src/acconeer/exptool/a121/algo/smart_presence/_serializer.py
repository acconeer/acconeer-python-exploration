# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

from typing import List, Optional, Sequence

import h5py
import numpy as np

from ._ref_app import RefAppResult


_ALL_REF_APP_RESULT_FIELDS = (
    "zone_limits",
    "presence_detected",
    "max_presence_zone",
    "total_zone_detections",
    "inter_presence_score",
    "inter_zone_detections",
    "max_inter_zone",
    "intra_presence_score",
    "intra_zone_detections",
    "max_intra_zone",
)


class PhonyNoneSeries:
    def __next__(self) -> None:
        return None

    def __iter__(self) -> PhonyNoneSeries:
        return self


def _serialize_optional_uint(num_list: List[Optional[int]]) -> List[int]:
    return [num if num is not None else -1 for num in num_list]


def _deserialize_optional_uint(num: int) -> Optional[int]:
    return None if num == -1 else num


class RefAppResultListH5Serializer:
    """
    Reads or writes a smart presence RefAppResult from/to a given h5py.Group
    """

    def __init__(
        self,
        group: h5py.Group,
        fields: Sequence[str] = _ALL_REF_APP_RESULT_FIELDS,
        allow_missing_fields: bool = False,
    ) -> None:
        """
        :param group: The H5 group that will have datasets read/written to it
        :param fields: The fields to serialize. Has no effect on deserialization
        :param allow_missing_fields:
            Whether it's acceptable to break type safety during de-serialization
            by replacing missing fields by ``None``. Has no effect on serialization.
        """
        self.group = group
        self.fields = fields
        self.allow_missing_fields = allow_missing_fields

    def serialize(self, results: List[RefAppResult]) -> None:
        if "zone_limits" in self.fields:
            self.group.create_dataset(
                "zone_limits",
                dtype=float,
                data=np.array([res.zone_limits for res in results]),
                track_times=False,
            )

        if "presence_detected" in self.fields:
            self.group.create_dataset(
                "presence_detected",
                dtype=bool,
                data=np.array([res.presence_detected for res in results]),
                track_times=False,
            )

        if "max_presence_zone" in self.fields:
            data = np.array(_serialize_optional_uint([res.max_presence_zone for res in results]))

            self.group.create_dataset(
                "max_presence_zone",
                dtype=int,
                data=data,
                track_times=False,
            )

        if "total_zone_detections" in self.fields:
            self.group.create_dataset(
                "total_zone_detections",
                dtype=int,
                data=np.array([res.total_zone_detections for res in results]),
                track_times=False,
            )

        if "inter_presence_score" in self.fields:
            self.group.create_dataset(
                "inter_presence_score",
                dtype=float,
                data=np.array([res.inter_presence_score for res in results]),
                track_times=False,
            )

        if "inter_zone_detections" in self.fields:
            self.group.create_dataset(
                "inter_zone_detections",
                dtype=int,
                data=np.array([res.inter_zone_detections for res in results]),
                track_times=False,
            )

        if "max_inter_zone" in self.fields:
            data = np.array(_serialize_optional_uint([res.max_inter_zone for res in results]))

            self.group.create_dataset(
                "max_inter_zone",
                dtype=int,
                data=data,
                track_times=False,
            )

        if "intra_presence_score" in self.fields:
            self.group.create_dataset(
                "intra_presence_score",
                dtype=float,
                data=np.array([res.intra_presence_score for res in results]),
                track_times=False,
            )

        if "intra_zone_detections" in self.fields:
            self.group.create_dataset(
                "intra_zone_detections",
                dtype=int,
                data=np.array([res.intra_zone_detections for res in results]),
                track_times=False,
            )

        if "max_intra_zone" in self.fields:
            data = np.array(_serialize_optional_uint([res.max_intra_zone for res in results]))

            self.group.create_dataset(
                "max_intra_zone",
                dtype=int,
                data=data,
                track_times=False,
            )

    def deserialize(self, _: None) -> List[RefAppResult]:
        groups = (
            self.group.get("zone_limits", PhonyNoneSeries()),
            self.group.get("presence_detected", PhonyNoneSeries()),
            self.group.get("max_presence_zone", PhonyNoneSeries()),
            self.group.get("total_zone_detections", PhonyNoneSeries()),
            self.group.get("inter_presence_score", PhonyNoneSeries()),
            self.group.get("inter_zone_detections", PhonyNoneSeries()),
            self.group.get("max_inter_zone", PhonyNoneSeries()),
            self.group.get("intra_presence_score", PhonyNoneSeries()),
            self.group.get("intra_zone_detections", PhonyNoneSeries()),
            self.group.get("max_intra_zone", PhonyNoneSeries()),
        )

        if any(isinstance(g, PhonyNoneSeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(isinstance(group, PhonyNoneSeries) for group in groups):
            return []

        return [
            RefAppResult(
                zone_limits=zone_limits,
                presence_detected=presence_detected,
                max_presence_zone=_deserialize_optional_uint(max_presence_zone),
                total_zone_detections=total_zone_detections,
                inter_presence_score=inter_presence_score,
                inter_zone_detections=inter_zone_detections,
                max_inter_zone=_deserialize_optional_uint(max_inter_zone),
                intra_presence_score=intra_presence_score,
                intra_zone_detections=intra_zone_detections,
                max_intra_zone=_deserialize_optional_uint(max_intra_zone),
            )
            for (
                zone_limits,
                presence_detected,
                max_presence_zone,
                total_zone_detections,
                inter_presence_score,
                inter_zone_detections,
                max_inter_zone,
                intra_presence_score,
                intra_zone_detections,
                max_intra_zone,
            ) in zip(*groups)
        ]
