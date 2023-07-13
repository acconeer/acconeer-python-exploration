# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

import typing as t

from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import processor_main

from . import Processor, ProcessorConfig, get_close_sensor_config
from ._blinkstick_updater import BlinkstickUpdater
from ._plugin import PlotPlugin


def _processor_getter(
    metadata: t.Union[a121.Metadata, t.List[t.Dict[int, a121.Metadata]]]
) -> Processor:
    if isinstance(metadata, list):
        raise RuntimeError("Metadata is unexpectedly extended")

    return Processor(
        sensor_config=get_close_sensor_config(),
        metadata=metadata,
        processor_config=ProcessorConfig(),
    )


processor_main(
    processor_getter=_processor_getter,
    plot_plugin=PlotPlugin,
    sensor_config_getter=get_close_sensor_config,
    _blinkstick_updater_cls=BlinkstickUpdater,
)
