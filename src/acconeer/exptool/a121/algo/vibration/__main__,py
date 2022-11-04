# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.a121.algo._plugins import processor_main

from . import Processor, ProcessorConfig, get_sensor_config
from ._plugin import PlotPlugin


processor_main(
    processor_cls=Processor,
    processor_config_cls=ProcessorConfig,
    plot_plugin=PlotPlugin,
    sensor_config_getter=get_sensor_config,
)
