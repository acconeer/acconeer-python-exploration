# Copyright (c) Acconeer AB, 2024
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

import acconeer.exptool.a121.algo.hand_motion as hm
from acconeer.exptool import a121
from acconeer.exptool.a121._core_ext import _ReplayingClient
from acconeer.exptool.a121.algo.hand_motion._mode_handler import (
    AppMode,
    DetectionState,
    _load_algo_data,
)


@attrs.frozen
class ResultSlice:
    app_mode: AppMode
    detection_state: t.Optional[DetectionState]
    # omits extra_result

    @classmethod
    def from_app_result(cls, app_result: hm.ModeHandlerResult) -> te.Self:
        return cls(
            app_mode=app_result.app_mode,
            detection_state=app_result.detection_state,
        )


@attrs.mutable
class AppWrapper:
    app: hm.ModeHandler

    def __getattr__(self, name: str) -> t.Any:
        return getattr(self.app, name)

    def get_next(self) -> ResultSlice:
        return ResultSlice.from_app_result(self.app.get_next())


def hand_motion_app(record: a121.H5Record) -> AppWrapper:
    algo_group = record.get_algo_group("hand_motion")
    sensor_id, config = _load_algo_data(algo_group)
    client = _ReplayingClient(record, realtime_replay=False)

    app = AppWrapper(
        hm.ModeHandler(client=client, sensor_id=sensor_id, mode_handler_config=config)
    )

    app.start()

    return app
