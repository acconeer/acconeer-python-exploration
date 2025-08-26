# Copyright (c) Acconeer AB, 2025
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import cargo


@attrs.frozen
class ResultSlice:
    presence_detected: t.Optional[bool] = attrs.field()
    inter_presence_score: t.Optional[float] = attrs.field()
    intra_presence_score: t.Optional[float] = attrs.field()
    distance: t.Optional[float] = attrs.field()
    level_m: t.Optional[float] = attrs.field()
    level_percent: t.Optional[float] = attrs.field()

    # Omitted:
    # mode: _Mode = attrs.field()
    # distance_processor_result: Optional[List[DistanceProcessorResult]] = attrs.field()
    # service_result: a121.Result = attrs.field()

    @classmethod
    def from_ex_app_result(cls, ex_app_result: cargo.ExAppResult) -> te.Self:
        return cls(
            presence_detected=ex_app_result.presence_detected,
            inter_presence_score=ex_app_result.inter_presence_score,
            intra_presence_score=ex_app_result.intra_presence_score,
            distance=ex_app_result.distance,
            level_m=ex_app_result.level_m,
            level_percent=ex_app_result.level_percent,
        )


@attrs.mutable
class ExAppWrapper:
    ex_app: cargo.ExApp

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.ex_app, name)

    def get_next(self) -> ResultSlice:
        return ResultSlice.from_ex_app_result(self.ex_app.get_next())


def cargo_app(record: a121.H5Record) -> t.Any:
    client = _ReplayingClient(record, realtime_replay=False)

    (
        sensor_id,
        ex_app_config,
        ex_app_context,
    ) = cargo._ex_app._load_algo_data(record.get_algo_group("cargo"))

    app = ExAppWrapper(
        ex_app=cargo.ExApp(
            client=client,
            sensor_id=sensor_id,
            ex_app_config=ex_app_config,
            ex_app_context=ex_app_context,
        )
    )

    app.start()

    return app
