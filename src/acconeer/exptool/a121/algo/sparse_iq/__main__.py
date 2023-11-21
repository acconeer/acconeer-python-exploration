# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

import typing as t

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import processor_main

from . import Processor, ProcessorConfig, get_sensor_config
from ._plugin import PlotPlugin


def _processor_getter(
    session_config: a121.SessionConfig,
    processor_config: ProcessorConfig,
    ignored_metadata: t.Union[a121.Metadata, t.List[t.Dict[int, a121.Metadata]]],
) -> Processor:
    return Processor(
        session_config=session_config,
        processor_config=processor_config,
    )


def _session_config_getter(sensor_id: int) -> a121.SessionConfig:
    return a121.SessionConfig({sensor_id: get_sensor_config()}, extended=True)


processor_main(
    processor_getter=_processor_getter,
    plot_plugin=PlotPlugin,
    processor_config_getter=ProcessorConfig,
    session_config_getter=_session_config_getter,
)
