# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import time

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401
from PySide6.QtGui import QFont

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.breathing import Processor, ProcessorConfig, get_sensor_config


sensor_config = get_sensor_config()


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))
    metadata = client.setup_session(sensor_config)

    processor = Processor(
        sensor_config=sensor_config, processor_config=ProcessorConfig(), metadata=metadata
    )

    pg_updater = PGUpdater(sensor_config, metadata)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()
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
    client.close()


class PGUpdater:

    _TIME_SERIES_Y_SCALE_MARGIN_M = 0.0025
    _DATA_INIT_DURATION = 5.0

    def __init__(self, sensor_config: a121.SensorConfig, metadata: a121.Metadata):
        ...

    def setup(self, win):

        pens = [et.utils.pg_pen_cycler(i) for i in range(5)]
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kws = [dict(pen=pen, **symbol_kw) for pen in pens]

        font = QFont()
        font.setPixelSize(16.0)

        # time series plot
        self.time_series_plot = win.addPlot(row=0, col=0)
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.addLegend()
        self.time_series_plot.setLabel("left", "Displacement (m)")
        self.time_series_plot.setLabel("bottom", "Time")
        self.time_series_plot.addItem(pg.PlotDataItem())
        self.time_series_curve = []
        self.time_series_curve.append(self.time_series_plot.plot(**feat_kws[0]))
        self.time_series_curve.append(self.time_series_plot.plot(**feat_kws[1]))

        self.time_series_smooth_limits = et.utils.SmoothLimits()

        self.time_series_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.time_series_text_item.setFont(font)
        self.time_series_text_item.show()
        self.time_series_plot.addItem(self.time_series_text_item)

        # fft plot
        self.fft_plot = win.addPlot(row=1, col=0)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.addLegend()
        self.fft_plot.setLabel("left", "Power")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = self.fft_plot.plot(**feat_kws[0])
        self.fft_vert_line = pg.InfiniteLine(pen=pens[1])
        self.fft_plot.addItem(self.fft_vert_line)

        self.fft_smooth_max = et.utils.SmoothMax(tau_grow=0.5, tau_decay=2.0)

        self.fft_text_item = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
            color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
        )
        self.fft_text_item.setFont(font)
        self.fft_text_item.show()
        self.fft_plot.addItem(self.fft_text_item)

        self.start_time = time.time()

    def update(self, processor_result):
        time_series = processor_result.time_series
        distance_to_analyze_m = processor_result.distance_to_analyze_m
        z_abs_lp = processor_result.lp_psd
        freqs = processor_result.freqs
        breathing_rate = processor_result.breathing_rate
        fft_peak_location = processor_result.fft_peak_location

        # time series plot
        self.time_series_curve[0].setData(time_series)
        lim = self.time_series_smooth_limits.update(time_series)

        self.time_series_plot.setYRange(
            lim[0] - self._TIME_SERIES_Y_SCALE_MARGIN_M,
            lim[1] + self._TIME_SERIES_Y_SCALE_MARGIN_M,
        )
        text_y_pos = self.time_series_plot.getAxis("left").range[1] * 0.95
        text_x_pos = self.time_series_plot.getAxis("bottom").range[1] / 2.0
        self.time_series_text_item.setPos(text_x_pos, text_y_pos)
        self.time_series_text_item.setHtml(
            "Distance being visualized: " + "{:.2f}".format(distance_to_analyze_m) + " (m)"
        )

        # fft plot
        if (time.time() - self.start_time) < self._DATA_INIT_DURATION:
            self.fft_curve.setData(freqs, np.zeros_like(freqs))
            self.fft_plot.setYRange(0.0, 1.0)

            text_y_pos = self.fft_plot.getAxis("left").range[1] * 0.95
            text_x_pos = self.fft_plot.getAxis("bottom").range[1] / 2.0
            self.fft_text_item.setHtml("Acquiring data.")
        elif freqs is not None:
            assert z_abs_lp is not None
            assert breathing_rate is not None
            assert fft_peak_location is not None

            self.fft_curve.setData(freqs, z_abs_lp)
            self.fft_vert_line.setValue(fft_peak_location)
            lim = self.fft_smooth_max.update(z_abs_lp)
            self.fft_plot.setYRange(0.0, lim * 1.2)

            text_y_pos = self.fft_plot.getAxis("left").range[1] * 0.95
            text_x_pos = self.fft_plot.getAxis("bottom").range[1] / 2.0

            self.fft_text_item.setHtml(
                "Breathing rate: " + "{:.1f}".format(breathing_rate) + " per minute"
            )
        self.fft_text_item.setPos(text_x_pos, text_y_pos)

    @staticmethod
    def _format_string(string_to_display: str) -> str:
        return (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:15pt;">'
            "{}</span></div>".format(string_to_display)
        )


if __name__ == "__main__":
    main()
