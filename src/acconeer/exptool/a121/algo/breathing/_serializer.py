# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import h5py
import numpy as np

from acconeer.exptool.a121.algo.presence import (
    ProcessorExtraResult as PresenceProcessorExtraResult,
)
from acconeer.exptool.a121.algo.presence import ProcessorResult as PresenceProcessorResult
from acconeer.exptool.utils import PhonySeries  # type: ignore[import]

from ._processor import AppState, BreathingProcessorExtraResult, BreathingProcessorResult
from ._ref_app import RefAppResult


_ALL_REF_APP_RESULT_FIELDS = (
    "app_state",
    "distances_being_analyzed",
    # "presence_result", ignored by default
    "breathing_result",
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
            Whether it's acceptable to break type safety during deserialization
            by replacing missing fields by ``None``. Has no effect on serialization.
        """
        self.group = group
        self.fields = fields
        self.allow_missing_fields = allow_missing_fields

    def serialize(self, results: t.List[RefAppResult]) -> None:
        if "presence_result" in self.fields:
            raise NotImplementedError(
                "'presence_result' is not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        if "app_state" in self.fields:
            data = np.array([r.app_state.name.encode("utf-8") for r in results])

            self.group.create_dataset(
                "app_state", dtype=h5py.special_dtype(vlen=bytes), data=data, track_times=False
            )

        if "distances_being_analyzed" in self.fields:
            data = np.array(
                [
                    r.distances_being_analyzed
                    if r.distances_being_analyzed is not None
                    else [np.nan, np.nan]
                    for r in results
                ]
            )

            self.group.create_dataset(
                "distances_being_analyzed", dtype=float, data=data, track_times=False
            )

        if "breathing_result" in self.fields:
            data = np.array(
                [
                    r.breathing_result.breathing_rate
                    if r.breathing_result is not None
                    and r.breathing_result.breathing_rate is not None
                    else np.nan
                    for r in results
                ]
            )

            self.group.create_dataset(
                "breathing_result", dtype=float, data=data, track_times=False
            )

    def deserialize(self, _: None) -> t.List[RefAppResult]:
        if "presence_result" in self.fields:
            raise NotImplementedError(
                "'presence_result' is not serializable at the moment."
                + "Skip it by specifying which fields to serialize"
            )

        groups = (
            self.group.get("app_state", PhonySeries(None)),
            self.group.get("distances_being_analyzed", PhonySeries(None)),
            self.group.get("breathing_result", PhonySeries(None)),
        )

        if any(isinstance(g, PhonySeries) for g in groups) and not self.allow_missing_fields:
            raise ValueError("Some fields are missing while 'allow_missing_fields' is False.")

        if all(g is None for g in groups):
            return []

        return [
            RefAppResult(
                app_state=AppState[app_state.decode("utf-8")],
                distances_being_analyzed=tuple(  # type: ignore
                    [int(d) for d in distances_being_analyzed]
                )
                if not np.isnan(distances_being_analyzed[0])
                else None,
                presence_result=PresenceProcessorResult(
                    intra_presence_score=0.0,
                    intra=np.array([], dtype=float),
                    inter_presence_score=0.0,
                    inter=np.array([], dtype=float),
                    presence_distance=0.0,
                    presence_detected=False,
                    extra_result=PresenceProcessorExtraResult(
                        frame=np.array([], dtype=complex),
                        abs_mean_sweep=np.array([], dtype=float),
                        fast_lp_mean_sweep=np.array([], dtype=float),
                        slow_lp_mean_sweep=np.array([], dtype=float),
                        lp_noise=np.array([], dtype=float),
                        presence_distance_index=0,
                    ),
                ),
                breathing_result=None
                if AppState[app_state.decode("utf-8")] != AppState.ESTIMATE_BREATHING_RATE
                else BreathingProcessorResult(
                    breathing_rate=None,
                    extra_result=BreathingProcessorExtraResult(
                        psd=np.array([], dtype=float),
                        frequencies=np.array([], dtype=float),
                        breathing_motion=np.array([], dtype=float),
                        time_vector=np.array([], dtype=float),
                        breathing_rate_history=np.array([], dtype=float),
                        all_breathing_rate_history=np.array([], dtype=float),
                    ),
                )
                if np.isnan(breathing_result)
                else BreathingProcessorResult(
                    breathing_rate=breathing_result,
                    extra_result=BreathingProcessorExtraResult(
                        psd=np.array([], dtype=float),
                        frequencies=np.array([], dtype=float),
                        breathing_motion=np.array([], dtype=float),
                        time_vector=np.array([], dtype=float),
                        breathing_rate_history=np.array([], dtype=float),
                        all_breathing_rate_history=np.array([], dtype=float),
                    ),
                ),
            )
            for (
                app_state,
                distances_being_analyzed,
                breathing_result,
            ) in zip(*groups)
        ]
