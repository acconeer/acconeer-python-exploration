# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import h5py
import numpy as np

from acconeer.exptool.utils import PhonySeries  # type: ignore[import]

from ._processor import ProcessorLevelStatus
from ._ref_app import RefAppResult


_ALL_REF_APP_RESULT_FIELDS = (
    "peak_detected",
    "peak_status",
    "level",
    # "extra_result" ignored by default
)


class RefAppResultListH5Serializer:
    """
    Reads or writes a tank level RefAppResult from/to a given h5py.Group
    """

    def __init__(
        self,
        group: h5py.Group,
        fields: t.Sequence[str] = _ALL_REF_APP_RESULT_FIELDS,
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

    def serialize(self, results: t.List[RefAppResult]) -> None:
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        result_ready = np.array(
            [
                r.peak_detected is not None and r.peak_status is not None and r.level is not None
                for r in results
            ]
        )

        self.group.create_dataset("result_ready", dtype=bool, data=result_ready, track_times=False)

        if "peak_detected" in self.fields:
            data = np.array(
                [r.peak_detected if r.peak_detected is not None else False for r in results]
            )

            self.group.create_dataset("peak_detected", dtype=bool, data=data, track_times=False)

        if "peak_status" in self.fields:
            data = np.array(
                [
                    r.peak_status.name.encode("utf-8")
                    if r.peak_status is not None
                    else ProcessorLevelStatus.NO_DETECTION.name.encode("utf-8")
                    for r in results
                ]
            )

            self.group.create_dataset(
                "peak_status", dtype=h5py.special_dtype(vlen=bytes), data=data, track_times=False
            )

        if "level" in self.fields:
            data = np.array([r.level if r.level is not None else np.nan for r in results])

            self.group.create_dataset("level", dtype=float, data=data, track_times=False)

    def deserialize(self, _: None) -> t.List[RefAppResult]:
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        groups = (
            self.group.get("peak_detected", PhonySeries(None)),
            self.group.get("peak_status", PhonySeries(None)),
            self.group.get("level", PhonySeries(None)),
            self.group.get("result_ready", PhonySeries(None)),
        )

        if any(isinstance(g, PhonySeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(g is None for g in groups):
            return []

        return [
            RefAppResult(
                peak_detected=peak_detected if result_ready else None,
                peak_status=ProcessorLevelStatus[peak_status.decode("utf-8")]
                if peak_status is not None and result_ready
                else None,
                level=level if result_ready else None,
                extra_result=None,  # type: ignore[arg-type]
            )
            for (
                peak_detected,
                peak_status,
                level,
                result_ready,
            ) in zip(*groups)
        ]
