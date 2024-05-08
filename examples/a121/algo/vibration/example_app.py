# Copyright (c) Acconeer AB, 2024
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
    ExampleApp,
    ExampleAppConfig,
    ExampleAppResult,
    get_high_frequency_config,
)


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    example_app_config = get_high_frequency_config()

    client = a121.Client.open(**a121.get_client_args(args))

    example_app = ExampleApp(
        client=client,
        sensor_id=SENSOR_ID,
        example_app_config=example_app_config,
    )

    pg_updater = PGUpdater(example_app_config)
    pg_process = et.PGProcess(pg_updater)

    example_app.start()
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        example_app_result = example_app.get_next()

        try:
            pg_process.put_data(example_app_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    example_app.stop()


class PGUpdater:
    def __init__(self, example_app_config: ExampleAppConfig):
        self.sensor_config = ExampleApp._get_sensor_config(example_app_config)
        self.meas_dist_m = example_app_config.measured_point * APPROX_BASE_STEP_LENGTH_M

    def setup(self, win):
        pen_blue = et.utils.pg_pen_cycler(0)
        pen_orange = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(0)
        brush_dot = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw_blue = dict(pen=pen_blue, **symbol_kw)
        feat_kw_orange = dict(pen=pen_orange)
        symbol_dot_kw = dict(symbol="o", symbolSize=10, symbolBrush=brush_dot, symbolPen="k")

        # presence plot
        self.object_detection_plot = pg.PlotItem()
        self.object_detection_plot.setMenuEnabled(False)
        self.object_detection_plot.showGrid(x=False, y=True)
        self.object_detection_plot.setLabel("left", "Max amplitude")
        self.object_detection_plot.setLabel("bottom", "Distance (m)")
        self.object_detection_plot.setXRange(self.meas_dist_m - 0.001, self.meas_dist_m + 0.001)
        self.presence_curve = self.object_detection_plot.plot(
            **dict(pen=pen_blue, **symbol_dot_kw)
        )

        self.presence_threshold = pg.InfiniteLine(pen=pen_blue, angle=0)
        self.object_detection_plot.addItem(self.presence_threshold)
        self.presence_threshold.show()

        self.smooth_max_presence = et.utils.SmoothMax(tau_decay=10.0)

        # sweep and threshold plot
        self.time_series_plot = pg.PlotItem()
        self.time_series_plot.setMenuEnabled(False)
        self.time_series_plot.showGrid(x=True, y=True)
        self.time_series_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.time_series_plot.setLabel("bottom", "History")
        self.time_series_curve = self.time_series_plot.plot(**feat_kw_blue)

        self.time_series_plot.setYRange(-1000, 1000)
        self.time_series_plot.setXRange(0, 1024)

        self.text_item_time_series = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.text_item_time_series.hide()
        self.time_series_plot.addItem(self.text_item_time_series)

        sublayout = win.addLayout(row=0, col=0)
        sublayout.layout.setColumnStretchFactor(1, 5)
        sublayout.addItem(self.object_detection_plot, row=0, col=0)
        sublayout.addItem(self.time_series_plot, row=0, col=1)

        self.smooth_lim_time_series = et.utils.SmoothLimits(tau_decay=0.5, tau_grow=0.1)

        self.fft_plot = win.addPlot(col=0, row=1)
        self.fft_plot.setMenuEnabled(False)
        self.fft_plot.showGrid(x=True, y=True)
        self.fft_plot.setLabel("left", "Displacement (<font>&mu;</font>m)")
        self.fft_plot.setLabel("bottom", "Frequency (Hz)")
        self.fft_plot.setLogMode(False, True)
        self.fft_plot.addItem(pg.PlotDataItem())
        self.fft_curve = [
            self.fft_plot.plot(**feat_kw_blue),
            self.fft_plot.plot(**feat_kw_orange),
            self.fft_plot.plot(**dict(pen=pen_blue, **symbol_dot_kw)),
        ]

        self.text_item_fft = pg.TextItem(
            fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
            anchor=(0.5, 0),
        )
        self.text_item_fft.hide()
        self.fft_plot.addItem(self.text_item_fft)

        self.smooth_max_fft = et.utils.SmoothMax()

    def update(self, example_app_result: ExampleAppResult) -> None:
        # Extra result
        time_series = example_app_result.processor_extra_result.zm_time_series
        lp_displacements_threshold = (
            example_app_result.processor_extra_result.lp_displacements_threshold
        )
        amplitude_threshold = example_app_result.processor_extra_result.amplitude_threshold

        # Processor result
        lp_displacements = example_app_result.lp_displacements
        lp_displacements_freqs = example_app_result.lp_displacements_freqs
        max_amplitude = example_app_result.max_sweep_amplitude
        max_displacement = example_app_result.max_displacement
        max_displacement_freq = example_app_result.max_displacement_freq
        time_series_rms = example_app_result.time_series_std

        # Plot object presence metric
        self.presence_curve.setData([self.meas_dist_m], [max_amplitude])
        self.presence_threshold.setValue(amplitude_threshold)
        lim = self.smooth_max_presence.update(max_amplitude)
        self.object_detection_plot.setYRange(0, max(1000.0, lim))

        # Plot time series
        if time_series is not None and amplitude_threshold < max_amplitude:
            assert time_series_rms is not None
            lim = self.smooth_lim_time_series.update(time_series)
            self.time_series_plot.setYRange(lim[0], lim[1])
            self.time_series_plot.setXRange(0, time_series.shape[0])

            self.text_item_time_series.setPos(time_series.size / 2, lim[1] * 0.95)
            html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:15pt;">'
                "{}</span></div>".format("RMS : " + str(int(time_series_rms)))
            )
            self.text_item_time_series.setHtml(html_format)
            self.text_item_time_series.show()
            self.time_series_curve.setData(time_series)

        # Plot spectrum
        if lp_displacements is not None:
            assert time_series is not None
            assert lp_displacements is not None

            self.fft_curve[0].setData(lp_displacements_freqs, lp_displacements)
            self.fft_curve[1].setData(lp_displacements_freqs, lp_displacements_threshold)
            lim = self.smooth_max_fft.update(np.max(lp_displacements))
            self.fft_plot.setYRange(-1, np.log10(lim))

            if max_displacement_freq is not None and max_displacement is not None:
                self.fft_curve[2].setData([max_displacement_freq], [max_displacement])

                # Place text box centered at the top of the plotting window
                self.text_item_fft.setPos(max(lp_displacements_freqs) / 2, np.log10(lim) * 0.95)
                html_format = (
                    '<div style="text-align: center">'
                    '<span style="color: #FFFFFF;font-size:15pt;">'
                    "{}</span></div>".format(
                        "Frequency: "
                        + str(int(max_displacement_freq))
                        + "Hz Displacement: "
                        + str(int(max_displacement))
                        + "<font>&mu;</font>m"
                    )
                )
                self.text_item_fft.setHtml(html_format)
                self.text_item_fft.show()
            else:
                self.fft_curve[2].setData([], [])
                self.text_item_fft.hide()


if __name__ == "__main__":
    main()
