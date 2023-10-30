# Copyright (c) Acconeer AB, 2023
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_eq, attrs_ndarray_isclose
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import smart_presence
from acconeer.exptool.a121.algo.smart_presence import _ref_app as smart_presence_ref_app


@attrs.frozen
class RefAppResultSlice:
    max_inter_zone: t.Optional[int]
    max_intra_zone: t.Optional[int]
    max_presence_zone: t.Optional[int]

    zone_limits: npt.NDArray[np.float_] = attrs.field(eq=attrs_ndarray_isclose)
    total_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_eq)
    inter_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_eq)
    intra_zone_detections: npt.NDArray[np.int_] = attrs.field(eq=attrs_ndarray_eq)
    wake_up_detections: t.Optional[npt.NDArray[np.int_]] = attrs.field(eq=attrs_ndarray_eq)

    used_config: smart_presence_ref_app._Mode
    switch_delay: bool
    presence_detected: bool
    inter_presence_score: float = attrs.field(eq=attrs_ndarray_isclose)
    intra_presence_score: float = attrs.field(eq=attrs_ndarray_isclose)

    @classmethod
    def from_ref_app_result(cls, result: smart_presence.RefAppResult) -> te.Self:
        return cls(
            max_intra_zone=result.max_intra_zone,
            max_inter_zone=result.max_inter_zone,
            max_presence_zone=result.max_presence_zone,
            zone_limits=result.zone_limits,
            total_zone_detections=result.total_zone_detections,
            inter_zone_detections=result.inter_zone_detections,
            intra_zone_detections=result.intra_zone_detections,
            wake_up_detections=result.wake_up_detections,
            used_config=result.used_config,
            switch_delay=result.switch_delay,
            presence_detected=result.presence_detected,
            inter_presence_score=float(result.inter_presence_score),
            intra_presence_score=float(result.intra_presence_score),
        )


@attrs.mutable
class RefAppWrapper:
    ref_app: smart_presence.RefApp

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.ref_app, name)

    def get_next(self) -> RefAppResultSlice:
        return RefAppResultSlice.from_ref_app_result(self.ref_app.get_next())


def smart_presence_controller(record: a121.H5Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("smart_presence")
    sensor_id, config, context = smart_presence_ref_app._load_algo_data(algo_group)
    client = _ReplayingClient(record, realtime_replay=False)
    app = RefAppWrapper(
        smart_presence.RefApp(
            client=client,
            sensor_id=sensor_id,
            ref_app_config=config,
            ref_app_context=context,
        )
    )

    app.start()

    return app
