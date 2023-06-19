# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t
from typing import List, Optional, Sequence

import h5py
import numpy as np
import numpy.typing as npt

from ._ref_app import RefAppResult, _Mode


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
    "used_config",
    "wake_up_detections",
    "switch_delay",
    # "service_result" ignored by default
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


def _stack_optional_arraylike(
    sequence: t.Sequence[t.Optional[t.Union[t.List[t.Any], npt.NDArray[t.Any]]]],
    dtype: t.Union[t.Type[float], t.Type[complex]] = float,
) -> npt.NDArray[t.Any]:
    """
    Tries to create an NDArray from a sequence of Optional ArrayLikes, i.e.
    a sequence that looks something like

        [[1 2],
         None,
         [1 2 3 4],
         []
         ...
        ]

    ``None``/``[]`` are replaced with NaN-arrays that has the same dimensions as the
    largest non-NaN array in the sequence:

        [[1   2   NaN Nan],
         [NaN NaN NaN NaN],
         [1   2   3   4],
         [NaN NaN NaN NaN]
         ...
        ]
    """
    SENTINELS = {float: np.NAN, complex: np.NAN + 1j * np.NAN}
    dims = {np.ndim(x) for x in sequence if x is not None}

    if len(dims) > 1:
        raise ValueError(f"arrays in {sequence} are of different dimensions")

    (dim,) = dims
    if dim > 1:
        raise ValueError("cannot handle arrays with ndim > 1")

    lengths = {len(x) for x in sequence if x is not None}
    length = max(lengths)

    data_type = type(sequence[0][0]) if sequence[0] is not None and len(sequence[0]) > 0 else None
    data_type = float if data_type == np.int64 else data_type

    return np.stack(
        [
            np.full((length,), fill_value=SENTINELS[dtype], dtype=dtype)
            if x is None or np.size(x) < 0
            else np.pad(
                np.array(x, dtype=data_type),
                (0, length - len(x)),
                "constant",
                constant_values=(np.NaN, np.NaN),
            )
            for x in sequence
        ]
    )


def _remove_nans(x: npt.ArrayLike) -> npt.ArrayLike:
    if x is None:
        return None

    arr = np.array(x)

    return arr[~np.isnan(arr)]  # type: ignore[no-any-return]


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
        if "service_result" in self.fields:
            raise NotImplementedError(
                "'service_result' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "zone_limits" in self.fields:
            self.group.create_dataset(
                "zone_limits",
                dtype=float,
                data=_stack_optional_arraylike([res.zone_limits for res in results]),
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
                dtype=float,
                data=_stack_optional_arraylike([res.total_zone_detections for res in results]),
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
                dtype=float,
                data=_stack_optional_arraylike([res.inter_zone_detections for res in results]),
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
                dtype=float,
                data=_stack_optional_arraylike([res.intra_zone_detections for res in results]),
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

        if "used_config" in self.fields:
            self.group.create_dataset(
                "used_config",
                dtype=int,
                data=np.array([res.used_config.value for res in results]),
                track_times=False,
            )

        if "wake_up_detections" in self.fields:
            self.group.create_dataset(
                "wake_up_detections",
                dtype=int,
                data=np.array([res.wake_up_detections for res in results]),
                track_times=False,
            )

        if "switch_delay" in self.fields:
            self.group.create_dataset(
                "switch_delay",
                dtype=bool,
                data=np.array([res.switch_delay for res in results]),
                track_times=False,
            )

    def deserialize(self, _: None) -> List[RefAppResult]:
        if "service_result" in self.fields:
            raise NotImplementedError(
                "'service_result' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

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
            self.group.get("used_config", PhonyNoneSeries()),
            self.group.get("wake_up_detections", PhonyNoneSeries()),
            self.group.get("switch_delay", PhonyNoneSeries()),
        )

        if any(isinstance(g, PhonyNoneSeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(isinstance(group, PhonyNoneSeries) for group in groups):
            return []

        return [
            RefAppResult(
                zone_limits=_remove_nans(zone_limits),  # type: ignore[arg-type]
                presence_detected=presence_detected,
                max_presence_zone=_deserialize_optional_uint(max_presence_zone),
                total_zone_detections=_remove_nans(total_zone_detections),  # type: ignore[arg-type]
                inter_presence_score=inter_presence_score,
                inter_zone_detections=_remove_nans(inter_zone_detections),  # type: ignore[arg-type]
                max_inter_zone=_deserialize_optional_uint(max_inter_zone),
                intra_presence_score=intra_presence_score,
                intra_zone_detections=_remove_nans(intra_zone_detections),  # type: ignore[arg-type]
                max_intra_zone=_deserialize_optional_uint(max_intra_zone),
                used_config=(
                    None if used_config is None else _Mode(used_config)  # type: ignore[arg-type]
                ),
                wake_up_detections=wake_up_detections,
                switch_delay=switch_delay,
                service_result=None,  # type: ignore[arg-type]
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
                used_config,
                wake_up_detections,
                switch_delay,
            ) in zip(*groups)
        ]
