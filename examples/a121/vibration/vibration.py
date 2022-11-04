# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import APPROX_BASE_STEP_LENGTH_M
from acconeer.exptool.a121.algo.vibration import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
    ProcessorResult,
    get_sensor_config,
)


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    sensor_config = get_sensor_config()

    client = a121.Client(**a121.get_client_args(args))
    client.connect()
    metadata = client.setup_session(sensor_config)

    processor = Processor(
        sensor_config=sensor_config,
        metadata=metadata,
        processor_config=ProcessorConfig(),
        context=ProcessorContext(),
    )
    pg_updater = PGUpdater(sensor_config)
    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    client.start_session()
    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        result = client.get_next()
        plot_data = processor.process(result)
        try:
            pg_process.put_data(plot_data)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    client.disconnect()


class PGUpdater:
    def __init__(self, sensor_config):
        self.meas_dist_m = sensor_config.start_point * APPROX_BASE_STEP_LENGTH_M

    def setup(self, win):

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush, symbolPen="k")

        # precense plot
        self.precense_plot = pg.PlotItem()
        self.precense_plot.setMenuEnabled(False)
        self.precense_plot.showGrid(x=False, y=True)
        self.precense_plot.setLabel("left", "Max amplitude")
        self.precense_plot.setLabel("bottom", "Distance (m)")
        self.precense_plot.setXRange(self.meas_dist_m - 0.001, self.meas_dist_m + 0.001)
        self.precense_curve = self.precense_plot.plot(**dict(pen=pen, **symbol_dot_kw))

        self.smooth_max_precense = et.utils.SmoothMax(tau_decay=10.0)

        # sweep and threshold plot
        self.time_series_plot = pg.PlotItem()
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.setLabel("left", "Displacement (mm)")
        self.time_series_plot.setLabel("bottom", "History")
        self.time_series_curve = self.time_series_plot.plot(**feat_kw)

        sublayout = win.addLayout(row=0, col=0)
        sublayout.layout.setColumnStretchFactor(1, 5)
        sublayout.addItem(self.precense_plot, row=0, col=0)
        sublayout.addItem(self.time_series_plot, row=0, col=1)

        self.smooth_lim_time_series = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

        self.fft_plot = win.addPlot(col=0, row=1)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.setLabel("left", "Power (db)")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = self.fft_plot.plot(**feat_kw)

        self.smooth_max_fft = et.utils.SmoothMax()

    def update(self, processor_result: ProcessorResult) -> None:

        time_series = processor_result.time_series
        z_abs_db = processor_result.lp_z_abs_db
        freqs = processor_result.freqs
        max_amplitude = processor_result.max_amplitude

        self.precense_curve.setData([self.meas_dist_m], [max_amplitude])
        lim = self.smooth_max_precense.update(max_amplitude)
        self.precense_plot.setYRange(0, max(1000.0, lim))

        self.time_series_curve.setData(time_series)
        lim = self.smooth_lim_time_series.update(time_series)
        self.time_series_plot.setYRange(lim[0], lim[1])

        self.fft_curve.setData(freqs, z_abs_db)
        lim = self.smooth_max_fft.update(np.max(z_abs_db))
        self.fft_plot.setYRange(0, lim)


if __name__ == "__main__":
    main()
