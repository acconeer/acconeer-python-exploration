from __future__ import annotations

from typing import Any, Callable, Type

import attrs

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121 import algo
from acconeer.exptool.app.new import GeneralMessage

from ._null_app_model import NullAppModel
from .processor import ProcessorPlotPluginBase


def processor_main(
    *,
    processor_cls: Type[algo.ProcessorBase],
    processor_config_cls: Type[algo.AlgoConfigBase],
    plot_plugin: Type[ProcessorPlotPluginBase],
    sensor_config_getter: Callable[[], a121.SensorConfig],
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
    assert isinstance(metadata, a121.Metadata)

    processor_config = processor_config_cls()

    processor = processor_cls(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )

    pg_updater = ProcessorPGUpdater(
        plot_plugin=plot_plugin,
        sensor_config=sensor_config,
        metadata=metadata,
    )
    pg_process = et.PGProcess(pg_updater)  # type: ignore[attr-defined]
    pg_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        assert isinstance(result, a121.Result)

        processor_result = processor.process(result)

        try:
            pg_process.put_data(processor_result)
        except et.PGProccessDiedException:  # type: ignore[attr-defined]
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


@attrs.mutable(kw_only=True, slots=False)
class ProcessorPGUpdater:
    plot_plugin: Type[ProcessorPlotPluginBase] = attrs.field()
    sensor_config: a121.SensorConfig = attrs.field()
    metadata: a121.Metadata = attrs.field()

    def setup(self, win: pg.GraphicsLayout) -> None:
        self.plot_plugin_obj = self.plot_plugin(plot_layout=win, app_model=NullAppModel())
        self.plot_plugin_obj.handle_message(
            GeneralMessage(
                name="setup", kwargs=dict(sensor_config=self.sensor_config, metadata=self.metadata)
            )
        )

    def update(self, data: Any) -> None:
        self.plot_plugin_obj.handle_message(GeneralMessage(name="plot", data=data))
        self.plot_plugin_obj.draw()
