# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import INT_16_COMPLEX, complex_array_to_int16_complex
from acconeer.exptool.a121._core.entities.containers.utils import int16_complex_array_to_complex
from acconeer.exptool.utils import PhonySeries  # type: ignore[import]

from ._detector import DetectorResult
from ._processors import ProcessorResult


_ALL_PROCESSOR_RESULT_FIELDS = (
    "estimated_distances",
    "estimated_strengths",
    "near_edge_status",
    "recorded_threshold_mean_sweep",
    "recorded_threshold_noise_std",
    "direct_leakage",
    "phase_jitter_comp_reference",
    # "extra_result" ignored by default
)

_ALL_DETECTOR_RESULT_FIELDS = (
    "strengths",
    "distances",
    "near_edge_status",
    "processor_results",
    "service_extended_result",
)

_INT_16_COMPLEX_SENTINEL = -(2**15)


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


class ProcessorResultListH5Serializer:
    """
    Reads or writes a distance ProcessorResult from/to a given h5py.Group
    """

    def __init__(
        self,
        group: h5py.Group,
        fields: t.Sequence[str] = _ALL_PROCESSOR_RESULT_FIELDS,
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

        if "estimated_distances" in self.fields:
            data = _stack_optional_arraylike([r.estimated_distances for r in results])

            self.group.create_dataset(
                "estimated_distances",
                dtype=float,
                data=data,
                track_times=False,
            )

        if "estimated_strengths" in self.fields:
            data = _stack_optional_arraylike([r.estimated_strengths for r in results])

            self.group.create_dataset(
                "estimated_strengths",
                dtype=float,
                data=data,
                track_times=False,
            )

        if "near_edge_status" in self.fields:
            near_data = np.array([r.near_edge_status for r in results])

            self.group.create_dataset(
                "near_edge_status",
                dtype=bool,
                data=near_data,
                track_times=False,
            )

        if "recorded_threshold_mean_sweep" in self.fields:
            data = _stack_optional_arraylike([r.recorded_threshold_mean_sweep for r in results])

            self.group.create_dataset(
                "recorded_threshold_mean_sweep",
                dtype=float,
                data=data,
                track_times=False,
            )

        if "recorded_threshold_noise_std" in self.fields:
            data = _stack_optional_arraylike([r.recorded_threshold_noise_std for r in results])

            self.group.create_dataset(
                "recorded_threshold_noise_std",
                dtype=float,
                data=data,
                track_times=False,
            )

        if "direct_leakage" in self.fields:
            data = _stack_optional_arraylike([r.direct_leakage for r in results], dtype=complex)
            # replaces NaNs with int-sentinels before int_16_complex-conversion
            # since NaN becomes 0 at conversion
            data = np.array(
                [
                    np.full(x.shape, fill_value=_INT_16_COMPLEX_SENTINEL * (1 + 1j))
                    if np.isnan(x).all()
                    else x
                    for x in data
                ]
            )

            self.group.create_dataset(
                "direct_leakage",
                dtype=INT_16_COMPLEX,
                data=complex_array_to_int16_complex(data),
                track_times=False,
            )

        if "phase_jitter_comp_reference" in self.fields:
            data = _stack_optional_arraylike(
                [
                    res.phase_jitter_comp_reference.reshape((1, -1)).squeeze()
                    if res.phase_jitter_comp_reference is not None
                    else None
                    for res in results
                ]
            )

            self.group.create_dataset(
                "phase_jitter_comp_reference",
                dtype=float,
                data=data,
                track_times=False,
            )

    @staticmethod
    def _replace_if_all_is_nan(
        x: t.Optional[npt.ArrayLike], replacement: t.Any = None
    ) -> t.Union[npt.ArrayLike, t.Any]:
        if x is None:
            return replacement

        return replacement if np.isnan(x).all() else x

    @staticmethod
    def _direct_leakage_deserialize(
        x: t.Optional[npt.NDArray[t.Any]],
    ) -> t.Optional[npt.NDArray[t.Any]]:
        if x is None:
            return None
        elif (x == np.array(-(2**15), dtype=INT_16_COMPLEX)).all():
            return None
        else:
            return int16_complex_array_to_complex(x)

    def deserialize(self, _: None) -> t.List[ProcessorResult]:
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        groups = (
            self.group.get("estimated_distances", PhonySeries([], is_prototype_singleton=False)),
            self.group.get("estimated_strengths", PhonySeries([], is_prototype_singleton=False)),
            self.group.get("near_edge_status", PhonySeries(None)),
            self.group.get("recorded_threshold_mean_sweep", PhonySeries(None)),
            self.group.get("recorded_threshold_noise_std", PhonySeries(None)),
            self.group.get("direct_leakage", PhonySeries(None)),
            self.group.get("phase_jitter_comp_reference", PhonySeries(None)),
        )

        if any(isinstance(g, PhonySeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(isinstance(group, PhonySeries) for group in groups):
            return []

        return [
            ProcessorResult(
                estimated_distances=self._replace_if_all_is_nan(  # type: ignore[arg-type]
                    est_dists,
                ),
                estimated_strengths=self._replace_if_all_is_nan(  # type: ignore[arg-type]
                    est_strengths,
                ),
                near_edge_status=(
                    self._replace_if_all_is_nan(near_edge_status)  # type: ignore[arg-type]
                ),
                recorded_threshold_mean_sweep=(
                    self._replace_if_all_is_nan(rt_mean_sweep)  # type: ignore[arg-type]
                ),
                recorded_threshold_noise_std=(
                    self._replace_if_all_is_nan(rt_noise_std)  # type: ignore[arg-type]
                ),
                direct_leakage=(self._direct_leakage_deserialize(direct_leakage)),
                phase_jitter_comp_reference=(
                    self._replace_if_all_is_nan(  # type: ignore[arg-type]
                        jitter_comp.reshape((-1, 1)) if jitter_comp is not None else None
                    )
                ),
                extra_result=None,  # type: ignore[arg-type]
            )
            for (
                est_dists,
                est_strengths,
                near_edge_status,
                rt_mean_sweep,
                rt_noise_std,
                direct_leakage,
                jitter_comp,
            ) in zip(*groups)
        ]


class DetectorResultListH5Serializer:
    """
    Reads or writes a list of dictionaries of int,
    distance DetectorResult from/to a given h5py.Group
    """

    def __init__(
        self,
        group: h5py.Group,
        fields: t.Sequence[str] = _ALL_DETECTOR_RESULT_FIELDS,
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

    def serialize(self, results: t.List[t.Dict[int, DetectorResult]]) -> None:
        if "processor_results" in self.fields:
            raise NotImplementedError(
                "'processor_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "service_extended_result" in self.fields:
            raise NotImplementedError(
                "'service_extended_result' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "strengths" in self.fields:
            data: t.Dict[int, t.List[t.Optional[npt.NDArray[t.Any]]]] = {}
            for res in results:
                for sensor_id, detector_result in res.items():
                    if sensor_id not in data:
                        data[sensor_id] = []
                    data[sensor_id].append(detector_result.strengths)

            strengths_data: t.Dict[int, npt.ArrayLike] = {}
            for sensor_id, strengths in data.items():
                strengths_data[sensor_id] = _stack_optional_arraylike(strengths)

            strengths_group = self.group.create_group("strengths")

            for sens, strengths_item in strengths_data.items():
                strengths_group.create_dataset(
                    str(sens),
                    dtype=float,
                    data=strengths_item,
                    track_times=False,
                )

        if "distances" in self.fields:
            data = {}
            for res in results:
                for sensor_id, detector_result in res.items():
                    if sensor_id not in data:
                        data[sensor_id] = []
                    data[sensor_id].append(detector_result.distances)

            distance_data: t.Dict[int, npt.ArrayLike] = {}
            for sensor_id, distances in data.items():
                distance_data[sensor_id] = _stack_optional_arraylike(distances)

            distances_group = self.group.create_group("distances")

            for sens, dist in distance_data.items():
                distances_group.create_dataset(
                    str(sens),
                    dtype=float,
                    data=dist,
                    track_times=False,
                )

        if "near_edge_status" in self.fields:
            near_data: t.Dict[int, t.List[t.Optional[bool]]] = {}
            for res in results:
                for sensor_id, detector_result in res.items():
                    if sensor_id not in near_data:
                        near_data[sensor_id] = []
                    near_data[sensor_id].append(detector_result.near_edge_status)

            near_edge_data: t.Dict[int, npt.ArrayLike] = {}
            for sensor_id, near_edge in near_data.items():
                near_edge_data[sensor_id] = np.array(near_edge)

            near_edge_group = self.group.create_group("near_edge_status")

            for sens, near in near_edge_data.items():
                near_edge_group.create_dataset(
                    str(sens),
                    dtype=bool,
                    data=near,
                    track_times=False,
                )

    def deserialize(self, _: None) -> t.List[t.Dict[int, DetectorResult]]:
        if "processor_results" in self.fields:
            raise NotImplementedError(
                "'processor_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "service_extended_result" in self.fields:
            raise NotImplementedError(
                "'service_extended_result' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        groups = (
            self.group.get("strengths", PhonySeries([], is_prototype_singleton=False)),
            self.group.get("distances", PhonySeries([], is_prototype_singleton=False)),
            self.group.get("near_edge_status", PhonySeries(None)),
        )

        if any(isinstance(g, PhonySeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(isinstance(group, PhonySeries) for group in groups):
            return []

        res = []
        (strengths, dists, near_edge_status) = groups

        for k in strengths.keys():
            for r, d, n in zip(strengths.get(k), dists.get(k), near_edge_status.get(k)):
                res.append(
                    {
                        int(k): DetectorResult(
                            strengths=r[~np.isnan(r)],
                            distances=d[~np.isnan(d)],
                            near_edge_status=(n),
                            processor_results=[],
                            service_extended_result=[],
                        )
                    }
                )

        return res
