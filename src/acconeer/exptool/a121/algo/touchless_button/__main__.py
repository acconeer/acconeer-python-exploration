# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved
from __future__ import annotations

import typing as t

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import processor_main

from . import Processor, ProcessorConfig, get_close_sensor_config
from ._blinkstick_updater import BlinkstickUpdater
from ._plugin import PlotPlugin


def _processor_getter(
    session_config: a121.SessionConfig,
    processor_config: ProcessorConfig,
    metadata: t.Union[a121.Metadata, t.List[t.Dict[int, a121.Metadata]]],
) -> Processor:
    if isinstance(metadata, list):
        msg = "Metadata is unexpectedly extended"
        raise RuntimeError(msg)

    return Processor(
        sensor_config=session_config.sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )


def _session_config_getter(sensor_id: int) -> a121.SessionConfig:
    return a121.SessionConfig({sensor_id: get_close_sensor_config()})


processor_main(
    processor_getter=_processor_getter,
    plot_plugin=PlotPlugin,
    session_config_getter=_session_config_getter,
    processor_config_getter=ProcessorConfig,
    _blinkstick_updater_cls=BlinkstickUpdater,
)
