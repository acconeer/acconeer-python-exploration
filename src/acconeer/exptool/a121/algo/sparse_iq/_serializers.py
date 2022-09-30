# Copyright (c) Acconeer AB, 2022
# All rights reserved

import json
import typing as t

import numpy as np

from acconeer.exptool.a121._core import complex_array_to_int16_complex

from ._processor import ProcessorResult


class ProcessorResultJSONEncoder(json.JSONEncoder):
    def default(self, o: t.Any) -> t.Any:
        if isinstance(o, ProcessorResult):
            result = o
            return dict(
                frame=complex_array_to_int16_complex(result.frame).tolist(),
                distance_velocity_map=result.distance_velocity_map.tolist(),
                amplitudes=result.amplitudes.tolist(),
                phases=result.phases.tolist(),
            )

        return super().default(o)


class ProcessorResultJSONDecoder(json.JSONDecoder):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(object_hook=self.object_hook, *args, **kwargs)

    @staticmethod
    def object_hook(obj: dict) -> ProcessorResult:
        real_frame = np.array(obj["frame"])[..., 0]
        imag_frame = np.array(obj["frame"])[..., 1]

        return ProcessorResult(
            frame=real_frame + 1j * imag_frame,
            distance_velocity_map=np.array(obj["distance_velocity_map"]),
            amplitudes=np.array(obj["amplitudes"]),
            phases=np.array(obj["phases"]),
        )


class ProcessorResultJSONSerializer:
    @staticmethod
    def serialize(result: ProcessorResult) -> str:
        return json.dumps(result, cls=ProcessorResultJSONEncoder)

    @staticmethod
    def deserialize(result: str) -> ProcessorResult:
        return json.loads(result, cls=ProcessorResultJSONDecoder)  # type: ignore[no-any-return]
