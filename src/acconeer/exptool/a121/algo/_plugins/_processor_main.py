# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Any, Callable, Generic, Optional, Type

import attrs

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool._bs_thread import BSThread, BSThreadDiedException  # type: ignore[import]
from acconeer.exptool.a121 import algo
from acconeer.exptool.a121.algo._base import InputT, MetadataT, ProcessorConfigT, ResultT
from acconeer.exptool.app.new import GeneralMessage

from ._null_app_model import NullAppModel
from .processor import GenericProcessorPlotPluginBase


def processor_main(
    *,
    processor_cls: Type[algo.GenericProcessorBase[InputT, ProcessorConfigT, ResultT, MetadataT]],
    processor_config_cls: Type[ProcessorConfigT],
    plot_plugin: Type[GenericProcessorPlotPluginBase[ResultT, MetadataT]],
    sensor_config_getter: Callable[[], a121.SensorConfig],
    _blinkstick_updater_cls: Optional[Any] = None,
) -> None:
    parser = a121.ExampleArgumentParser()
    parser.add_argument("--sensor", type=int, default=1)
    args = parser.parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    sensor_config = sensor_config_getter()
    session_config = a121.SessionConfig({args.sensor: sensor_config})

    metadata = client.setup_session(session_config)

    processor_config = processor_config_cls()

    processor = processor_cls(
        sensor_config=sensor_config,
        metadata=metadata,  # type: ignore[arg-type]
        processor_config=processor_config,
    )

    pg_updater = ProcessorPGUpdater[ResultT, MetadataT](
        plot_plugin=plot_plugin,
        sensor_config=sensor_config,
        metadata=metadata,  # type: ignore[arg-type]
    )
    pg_process = et.PGProcess(pg_updater)  # type: ignore[attr-defined]
    pg_process.start()

    if _blinkstick_updater_cls is None:
        bs_process = None
    else:
        bs_updater = _blinkstick_updater_cls()
        bs_process = BSThread(bs_updater)
        bs_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()

        processor_result = processor.process(result)  # type: ignore[arg-type]

        try:
            pg_process.put_data(processor_result)

            if bs_process is not None:
                bs_process.put_data(processor_result)
        except (et.PGProccessDiedException, BSThreadDiedException):  # type: ignore[attr-defined]
            break

    print("Disconnecting...")

    pg_process.close()

    if bs_process is not None:
        bs_process.close()

    client.disconnect()


@attrs.mutable(kw_only=True, slots=False)
class ProcessorPGUpdater(Generic[ResultT, MetadataT]):
    plot_plugin: Type[GenericProcessorPlotPluginBase[ResultT, MetadataT]] = attrs.field()
    sensor_config: a121.SensorConfig = attrs.field()
    metadata: MetadataT = attrs.field()
    plot_plugin_obj: Optional[GenericProcessorPlotPluginBase[ResultT, MetadataT]] = attrs.field(
        default=None, init=False
    )

    def setup(self, win: pg.GraphicsLayout) -> None:
        self.plot_plugin_obj = self.plot_plugin(plot_layout=win, app_model=NullAppModel())
        self.plot_plugin_obj.handle_message(
            GeneralMessage(
                name="setup", kwargs=dict(sensor_config=self.sensor_config, metadata=self.metadata)
            )
        )

    def update(self, data: Any) -> None:
        if self.plot_plugin_obj is None:
            raise RuntimeError

        self.plot_plugin_obj.handle_message(GeneralMessage(name="plot", data=data))
        self.plot_plugin_obj.draw()
