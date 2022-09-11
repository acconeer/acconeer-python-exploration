# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._utils import get_distances_m
from acconeer.exptool.a121.algo.phase_tracking import (
    Processor,
    ProcessorConfig,
    ProcessorContext,
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
    pg_updater = PGUpdater(sensor_config, metadata)
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
    def __init__(self, sensor_config: a121.SensorConfig, metadata: a121.Metadata):
        (self.distances_m, _) = get_distances_m(sensor_config, metadata)

    def setup(self, win):
        pens = [et.utils.pg_pen_cycler(i) for i in range(3)]
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kws = [dict(pen=pen, **symbol_kw) for pen in pens]

        # sweep and threshold plot
        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())
        self.sweeps_curve = [self.sweep_plot.plot(**feat_kw) for feat_kw in feat_kws]
        self.sweep_vertical_line = pg.InfiniteLine(pen=pens[2])
        self.sweep_plot.addItem(self.sweep_vertical_line)
        self.sweep_smooth_max = et.utils.SmoothMax()
        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweeps_curve[0], "Sweep")
        sweep_plot_legend.addItem(self.sweeps_curve[1], "Threshold")

        # argument plot
        argument_plot = win.addPlot(row=1, col=0)
        argument_plot.setMenuEnabled(False)
        argument_plot.showGrid(x=True, y=True)
        argument_plot.addLegend()
        argument_plot.setLabel("bottom", "Distance (m)")
        argument_plot.setLabel("left", "Phase")
        argument_plot.setYRange(-np.pi, np.pi)
        argument_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)
        argument_plot.setYRange(-np.pi, np.pi)
        argument_plot.addItem(pg.ScatterPlotItem())
        self.argument_curve = argument_plot.plot(
            **dict(pen=None, symbol="o", symbolSize=5, symbolPen="k")
        )
        self.argument_vertical_line = pg.InfiniteLine(pen=pens[2])
        argument_plot.addItem(self.argument_vertical_line)

        # history plot
        self.history_plot = win.addPlot(row=2, col=0)
        self.history_plot.setMenuEnabled(False)
        self.history_plot.showGrid(x=True, y=True)
        self.history_plot.addLegend()
        self.history_plot.setLabel("left", "Distance (mm)")
        self.history_plot.setLabel("bottom", "Time (s)")
        self.history_plot.addItem(pg.PlotDataItem())
        self.history_curve = self.history_plot.plot(**feat_kws[0])

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

    def update(self, processor_result):
        assert processor_result is not None
        assert processor_result.threshold is not None

        sweep = processor_result.lp_abs_sweep
        threshold = processor_result.threshold * np.ones(sweep.size)
        angle_sweep = processor_result.angle_sweep
        peak_loc = processor_result.peak_loc_m
        history = processor_result.distance_history
        rel_time_stamps = processor_result.rel_time_stamps

        # update sweep plot
        self.sweeps_curve[0].setData(self.distances_m, sweep)
        self.sweeps_curve[1].setData(self.distances_m, threshold)
        max_val_in_sweep_plot = max(np.max(sweep), np.max(threshold))
        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_sweep_plot))

        # update argument plot
        self.argument_curve.setData(self.distances_m, angle_sweep)

        if peak_loc is not None:
            # update vertical lines
            self.sweep_vertical_line.setValue(peak_loc)
            self.argument_vertical_line.setValue(peak_loc)
            self.sweep_vertical_line.show()
            self.argument_vertical_line.show()
        else:
            self.sweep_vertical_line.hide()
            self.argument_vertical_line.hide()

        if history is not None:
            # update history plot
            self.history_curve.setData(rel_time_stamps, history)
            lims = self.distance_hist_smooth_lim.update(history)
            self.history_plot.setYRange(lims[0], lims[1])
        self.history_plot.setXRange(-Processor.TIME_HORIZON_S, 0)


if __name__ == "__main__":
    main()
