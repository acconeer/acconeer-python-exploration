# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Optional, Type, Union

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool._bs_thread import BSThread, BSThreadDiedException  # type: ignore[import]
from acconeer.exptool.a121 import algo
from acconeer.exptool.a121.algo._base import InputT, ResultT
from acconeer.exptool.app.new.backend import GeneralMessage
from acconeer.exptool.app.new.pluginbase import PlotPluginBase

from ._null_app_model import NullAppModel


_ProcessorGetter = Callable[
    [Union[a121.Metadata, List[Dict[int, a121.Metadata]]]],
    algo.ProcessorBase[ResultT],
]


def processor_main(
    *,
    processor_getter: _ProcessorGetter[ResultT],
    plot_plugin: Type[PlotPluginBase],
    sensor_config_getter: Callable[[], a121.SensorConfig],
    _blinkstick_updater_cls: Optional[Any] = None,
) -> None:
    parser = a121.ExampleArgumentParser()
    parser.add_argument("--sensor", type=int, default=1)
    args = parser.parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    sensor_config = sensor_config_getter()
    session_config = a121.SessionConfig({args.sensor: sensor_config})

    metadata = client.setup_session(session_config)

    processor = processor_getter(metadata)

    qapp = QApplication()
    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOptions(antialias=True)

    plot_plugin_widget = plot_plugin(NullAppModel())
    plot_plugin_widget.handle_message(
        GeneralMessage(
            kwargs=dict(session_config=session_config, metadata=metadata),
            name="setup",
            recipient="plot_plugin",
        )
    )

    if _blinkstick_updater_cls is None:
        bs_process = None
    else:
        bs_updater = _blinkstick_updater_cls()
        bs_process = BSThread(bs_updater)
        bs_process.start()

    client.start_session()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    loop = get_loop(client, processor, plot_plugin_widget, bs_process)

    timer = QTimer()
    timer.timeout.connect(lambda: qapp.quit() if not next(loop) else None)
    timer.timeout.connect(lambda: qapp.quit() if interrupt_handler.got_signal else None)
    timer.start()

    plot_plugin_widget.show()
    qapp.exec()

    print("Disconnecting...")

    if bs_process is not None:
        bs_process.close()

    client.close()


def get_loop(
    client: a121.Client,
    processor: algo.GenericProcessorBase[InputT, ResultT],
    plot_plugin_widget: PlotPluginBase,
    blinkstick_process: Optional[BSThread],
) -> Iterator[bool]:
    while True:
        result = client.get_next()

        processor_result = processor.process(result)  # type: ignore[arg-type]

        plot_plugin_widget.handle_message(
            GeneralMessage(data=processor_result, name="plot", recipient="plot_plugin")
        )
        plot_plugin_widget.draw()

        if blinkstick_process is not None:
            try:
                blinkstick_process.put_data(processor_result)
            except BSThreadDiedException:
                break

        yield True

    yield False
