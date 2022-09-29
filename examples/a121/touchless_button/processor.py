# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.touchless_button import (
    Processor,
    ProcessorConfig,
    ProcessorResult,
    get_close_sensor_config,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    processor_config = ProcessorConfig()

    sensor_config = get_close_sensor_config()

    metadata = client.setup_session(sensor_config)
    client.start_session()

    processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=processor_config,
    )

    pg_updater = PGUpdater()
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        processor_result = processor.process(result)
        try:
            pg_process.put_data(processor_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.stop_session()
    client.disconnect()


class PGUpdater:
    def __init__(self):
        self.detection_history = np.full((2, 100), np.NaN)

    def setup(self, win):

        close_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Close detection")
        )
        far_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format("Far detection")
        )
        self.close_text_item = pg.TextItem(
            html=close_html,
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.far_text_item = pg.TextItem(
            html=far_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.detection_history_plot = win.addPlot(row=1, col=2)
        self.detection_history_plot.setMenuEnabled(False)
        self.detection_history_plot.setMouseEnabled(x=False, y=False)
        self.detection_history_plot.hideButtons()
        self.detection_history_plot.showGrid(x=True, y=True)
        self.detection_history_plot.setYRange(-0.1, 1.8)
        self.detection_history_curve_close = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(1, width=5)
        )
        self.detection_history_curve_far = self.detection_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0, width=5)
        )

        pos_top = (100 / 2, 1.8)
        pos_bottom = (100 / 2, 1.5)
        self.close_text_item.setPos(*pos_bottom)
        self.far_text_item.setPos(*pos_top)
        self.detection_history_plot.addItem(self.close_text_item)
        self.detection_history_plot.addItem(self.far_text_item)
        self.close_text_item.hide()
        self.far_text_item.hide()

    def update(self, result: ProcessorResult):
        detection = np.array([result.detection_close, result.detection_far])
        self.detection_history = np.roll(self.detection_history, -1, axis=1)
        self.detection_history[:, -1] = detection

        self.detection_history_curve_close.setData(self.detection_history[0])
        self.detection_history_curve_far.setData(self.detection_history[1])
        print(detection)

        if detection[0]:
            self.close_text_item.show()
        else:
            self.close_text_item.hide()

        if detection[1]:
            self.far_text_item.show()
        else:
            self.far_text_item.hide()


if __name__ == "__main__":
    main()
