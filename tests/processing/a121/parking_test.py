# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved
from __future__ import annotations

from typing import Optional

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo import parking
from acconeer.exptool.a121.algo.parking._ref_app import _load_algo_data


@attrs.frozen
class ResultSlice:
    car_detected: Optional[bool] = attrs.field()
    obstruction_detected: Optional[bool] = attrs.field()

    @classmethod
    def from_ref_app_result(cls, result: parking.RefAppResult) -> te.Self:
        return cls(
            car_detected=result.car_detected,
            obstruction_detected=result.obstruction_detected,
        )


@attrs.mutable
class RefAppWrapper:
    ref_app: parking.RefApp

    def __getattr__(self, name: str) -> te.Any:
        return getattr(self.ref_app, name)

    def get_next(self) -> ResultSlice:
        return ResultSlice.from_ref_app_result(self.ref_app.get_next())


def parking_default(record: a121.H5Record) -> RefAppWrapper:
    algo_group = record.get_algo_group("parking")
    sensor_id, config, context = _load_algo_data(algo_group)
    client = _ReplayingClient(record, realtime_replay=False)
    app = RefAppWrapper(
        parking.RefApp(
            client=client,
            sensor_id=sensor_id,
            ref_app_config=config,
            context=context,
        )
    )

    app.start()

    return app
