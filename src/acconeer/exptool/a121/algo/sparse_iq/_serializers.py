# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import json
import typing as t

import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import complex_array_to_int16_complex

from ._processor import ProcessorResult


S = t.TypeVar("S")
T = t.TypeVar("T")

_ALL_RESULT_FIELDS: t.Final = (
    "frame",
    "distance_velocity_map",
    "amplitudes",
    "phases",
)


_INCOMPLETE_SERIALIZATION_MSG = (
    f"Group does not contains all fields {_ALL_RESULT_FIELDS}."
    + "Use 'allow_missing_fields' to replace missing fields with None"
)


def optional_apply(func: t.Callable[[S], T]) -> t.Callable[[t.Optional[S]], t.Optional[T]]:
    def wrapper(arg: t.Optional[S]) -> t.Optional[T]:
        if arg is None:
            return None
        else:
            return func(arg)

    return wrapper


_maybe_ndarray = optional_apply(np.array)


@optional_apply
def _frame_preprocessing(json_frame: npt.NDArray) -> npt.NDArray[np.complex_]:
    """
    A "json_frame" has the ".real" & ".imag" in a 2-lenght-list in the innermost dimension.
    """
    return json_frame[..., 0] + 1j * json_frame[..., 1]  # type: ignore[no-any-return]


class ProcessorResultJSONEncoder(json.JSONEncoder):
    def __init__(self, *, fields: t.Sequence[str] = _ALL_RESULT_FIELDS, **kwargs: t.Any) -> None:
        super().__init__(**kwargs)
        self.fields = fields

    def default(self, o: t.Any) -> t.Any:
        if isinstance(o, ProcessorResult):
            result = o
            full_dict = dict(
                frame=complex_array_to_int16_complex(result.frame).tolist(),
                distance_velocity_map=result.distance_velocity_map.tolist(),
                amplitudes=result.amplitudes.tolist(),
                phases=result.phases.tolist(),
            )
            return {k: v for k, v in full_dict.items() if k in self.fields}

        return super().default(o)


class ProcessorResultJSONDecoder(json.JSONDecoder):
    def __init__(self, *, allow_missing_fields: bool = False, **kwargs: t.Any) -> None:
        super().__init__(object_hook=self.object_hook, **kwargs)
        self.allow_missing_fields = allow_missing_fields

    def object_hook(self, obj: dict) -> ProcessorResult:
        frame = _frame_preprocessing(_maybe_ndarray(obj.get("frame")))
        dvm = _maybe_ndarray(obj.get("distance_velocity_map"))
        amplitudes = _maybe_ndarray(obj.get("amplitudes"))
        phases = _maybe_ndarray(obj.get("phases"))

        if not self.allow_missing_fields and (
            frame is None or dvm is None or amplitudes is None or phases is None
        ):
            raise ValueError(_INCOMPLETE_SERIALIZATION_MSG)

        return ProcessorResult(
            frame=frame,  # type: ignore[arg-type]
            distance_velocity_map=dvm,  # type: ignore[arg-type]
            amplitudes=amplitudes,  # type: ignore[arg-type]
            phases=phases,  # type: ignore[arg-type]
        )


class ProcessorResultJSONSerializer:
    def __init__(
        self, fields: t.Sequence = _ALL_RESULT_FIELDS, allow_missing_fields: bool = False
    ) -> None:
        self.fields = fields
        self.allow_missing_fields = allow_missing_fields

    def serialize(self, result: ProcessorResult) -> str:
        return json.dumps(result, cls=ProcessorResultJSONEncoder, fields=self.fields)

    def deserialize(self, result: str) -> ProcessorResult:
        return json.loads(  # type: ignore[no-any-return]
            result, cls=ProcessorResultJSONDecoder, allow_missing_fields=self.allow_missing_fields
        )


class ProcessorResultListH5Serializer:
    """
    Reads or writes a SparseIQ ProcessorResult from/to a given h5py.Group
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
        if "frame" in self.fields:
            self.group.create_dataset(
                "frame",
                dtype=complex,
                data=np.stack([res.frame for res in results]),
                track_times=False,
            )

        if "distance_velocity_map" in self.fields:
            self.group.create_dataset(
                "distance_velocity_map",
                dtype=float,
                data=np.stack([res.distance_velocity_map for res in results]),
                track_times=False,
            )

        if "amplitudes" in self.fields:
            self.group.create_dataset(
                "amplitudes",
                dtype=float,
                data=np.stack([res.amplitudes for res in results]),
                track_times=False,
            )

        if "phases" in self.fields:
            self.group.create_dataset(
                "phases",
                dtype=float,
                data=np.stack([res.phases for res in results]),
                track_times=False,
            )

    def _deserialize_at_index(self, index: int) -> ProcessorResult:
        frames = self.group.get("frame", None)
        dvms = self.group.get("distance_velocity_map", None)
        ampss = self.group.get("amplitudes", None)
        phasess = self.group.get("phases", None)

        if not self.allow_missing_fields and (
            frames is None or dvms is None or ampss is None or phasess is None
        ):
            raise ValueError(_INCOMPLETE_SERIALIZATION_MSG)

        frame = None if (frames is None) else frames[index]
        dvm = None if (dvms is None) else dvms[index]
        amps = None if (ampss is None) else ampss[index]
        phases = None if (phasess is None) else phasess[index]

        return ProcessorResult(
            frame=frame,  # type: ignore[arg-type]
            distance_velocity_map=dvm,  # type: ignore[arg-type]
            amplitudes=amps,  # type: ignore[arg-type]
            phases=phases,  # type: ignore[arg-type]
        )

    def deserialize(self, _: None) -> t.List[ProcessorResult]:
        optional_lens = set(
            optional_apply(len)(series)
            for series in [
                self.group.get("frame", None),
                self.group.get("distance_velocity_map", None),
                self.group.get("amplitudes", None),
                self.group.get("phases", None),
            ]
        )
        lens = {l for l in optional_lens if l is not None}

        (common_length,) = lens

        return [self._deserialize_at_index(i) for i in range(int(common_length))]
