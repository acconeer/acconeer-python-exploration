# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

import copy
import typing as t

import h5py
import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import INT_16_COMPLEX, complex_array_to_int16_complex
from acconeer.exptool.a121._core.entities.containers.utils import int16_complex_array_to_complex

from ._processors import ProcessorResult


S = t.TypeVar("S")
T = t.TypeVar("T")
DTypeT = t.TypeVar("DTypeT")

_ALL_RESULT_FIELDS: t.Final = (
    "estimated_distances",
    "estimated_amplitudes",
    "recorded_threshold_mean_sweep",
    "recorded_threshold_noise_std",
    "direct_leakage",
    "phase_jitter_comp_reference",
    # "extra_result" ignored by default
)

_INT_16_COMPLEX_SENTINEL = -(2**15)


class PhonySeries(t.Generic[T]):
    def __init__(self, prototype: T, is_prototype_singleton: bool = True) -> None:
        self._prototype = prototype
        self._is_prototype_singleton = is_prototype_singleton

    def __next__(self) -> T:
        if self._is_prototype_singleton:
            return self._prototype
        else:
            return copy.copy(self._prototype)

    def __iter__(self) -> PhonySeries:
        return self


class ProcessorResultListH5Serializer:
    """
    Reads or writes a distance ProcessorResult from/to a given h5py.Group
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

    @staticmethod
    def _stack_optional_arraylike(
        sequence: t.Sequence[t.Optional[npt.ArrayLike]],
        dtype: t.Union[t.Type[float], t.Type[complex]] = float,
    ) -> npt.NDArray:
        """
        Tries to create an NDArray from a sequence of Optional ArrayLikes, i.e.
        a sequence that looks something like

            [[1 2 3],
             None,
             [1 2 3],
             ...
            ]

        ``None`` is replaced with a NaN-array that has the same dimensions as the
        non-NaN array in the sequence.
        """
        SENTINELS = {float: np.NAN, complex: np.NAN + 1j * np.NAN}
        shapes = {np.shape(x) for x in sequence if x is not None}

        if len(shapes) > 1:
            raise ValueError(f"arrays in {sequence} has different lengths.")
        elif len(shapes) == 0:
            raise ValueError("All elements in sequence are None")

        (shape,) = shapes

        return np.stack(
            [
                np.full(shape, fill_value=SENTINELS[dtype], dtype=dtype)
                if x is None
                else np.array(x)
                for x in sequence
            ]
        )

    def serialize(self, results: t.List[ProcessorResult]) -> None:
        if "extra_result" in self.fields:
            raise NotImplementedError(
                "'extra_results' are not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "estimated_distances" in self.fields:
            try:
                data = self._stack_optional_arraylike([r.estimated_distances for r in results])
            except ValueError:
                pass
            else:
                self.group.create_dataset(
                    "estimated_distances",
                    dtype=float,
                    data=data,
                    track_times=False,
                )

        if "estimated_amplitudes" in self.fields:
            try:
                data = self._stack_optional_arraylike([r.estimated_amplitudes for r in results])
            except ValueError:
                pass
            else:
                self.group.create_dataset(
                    "estimated_amplitudes",
                    dtype=float,
                    data=data,
                    track_times=False,
                )

        if "recorded_threshold_mean_sweep" in self.fields:
            try:
                data = self._stack_optional_arraylike(
                    [r.recorded_threshold_mean_sweep for r in results]
                )
            except ValueError:
                pass
            else:
                self.group.create_dataset(
                    "recorded_threshold_mean_sweep",
                    dtype=float,
                    data=data,
                    track_times=False,
                )

        if "recorded_threshold_noise_std" in self.fields:
            try:
                data = self._stack_optional_arraylike(
                    [r.recorded_threshold_noise_std for r in results]
                )
            except ValueError:
                pass
            else:
                self.group.create_dataset(
                    "recorded_threshold_noise_std",
                    dtype=float,
                    data=data,
                    track_times=False,
                )

        if "direct_leakage" in self.fields:
            try:
                data = self._stack_optional_arraylike(
                    [r.direct_leakage for r in results], dtype=complex
                )
            except ValueError:
                pass
            else:
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
            try:
                data = self._stack_optional_arraylike(
                    [res.phase_jitter_comp_reference for res in results]
                )
            except ValueError:
                pass
            else:
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
    def _direct_leakage_deserialize(x: t.Optional[npt.NDArray]) -> t.Optional[npt.NDArray]:
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
            self.group.get("estimated_amplitudes", PhonySeries([], is_prototype_singleton=False)),
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
                estimated_distances=self._replace_if_all_is_nan(
                    est_dists,
                ),  # type: ignore[arg-type]
                estimated_amplitudes=self._replace_if_all_is_nan(
                    est_amps,
                ),  # type: ignore[arg-type]
                recorded_threshold_mean_sweep=(
                    self._replace_if_all_is_nan(rt_mean_sweep)  # type: ignore[arg-type]
                ),
                recorded_threshold_noise_std=(
                    self._replace_if_all_is_nan(rt_noise_std)  # type: ignore[arg-type]
                ),
                direct_leakage=(self._direct_leakage_deserialize(direct_leakage)),
                phase_jitter_comp_reference=(
                    self._replace_if_all_is_nan(jitter_comp)  # type: ignore[arg-type]
                ),
                extra_result=None,  # type: ignore[arg-type]
            )
            for (
                est_dists,
                est_amps,
                rt_mean_sweep,
                rt_noise_std,
                direct_leakage,
                jitter_comp,
            ) in zip(*groups)
        ]
