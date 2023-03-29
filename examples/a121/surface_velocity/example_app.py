# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.surface_velocity import ExampleApp, ExampleAppConfig


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client(**a121.get_client_args(args))
    client.connect()

    example_app_config = ExampleAppConfig(
        surface_distance=0.40,
        sensor_angle=35,
        num_points=4,
        step_length=6,
        hwaas=16,
        sweeps_per_frame=128,
        sweep_rate=2000,
        time_series_length=1024,
    )

    example_app = ExampleApp(
        client=client,
        sensor_id=1,
        example_app_config=example_app_config,
    )
    example_app.start()

    pg_updater = PGUpdater(
        example_app_config,
    )

    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    print(f"Measured distances (m): {np.around(example_app.processor.distances, 2)}")

    while not interrupt_handler.got_signal:
        example_app_result = example_app.get_next()
        print(
            f"Estimated velocity {np.around(example_app_result.velocity, 2)} m/s, "
            f"at distance {np.around(example_app_result.distance_m, 2)} m"
        )

        try:
            pg_process.put_data(example_app_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


class PGUpdater:

    _VELOCITY_Y_SCALE_MARGIN_M = 0.25

    def __init__(
        self,
        example_app_config: ExampleAppConfig,
    ):
        self.slow_zone = example_app_config.slow_zone
        self.history_length_s = 10
        if example_app_config.frame_rate is None:
            estimated_frame_rate = (
                example_app_config.sweep_rate / example_app_config.sweeps_per_frame
            )
        else:
            estimated_frame_rate = example_app_config.frame_rate

        self.history_length_n = int(np.around(self.history_length_s * estimated_frame_rate))

        self.setup_is_done = False

    def setup(self, win):
        c0_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

        # Velocity plot

        self.velocity_history_plot = self._create_plot(win, row=0, col=0)
        self.velocity_history_plot.setTitle("Estimated velocity")
        self.velocity_history_plot.setLabel(axis="left", text="Velocity", units="m/s")
        self.velocity_history_plot.setLabel(axis="bottom", text="Time", units="s")
        self.velocity_history_plot.addLegend(labelTextSize="10pt")
        self.velocity_smooth_limits = et.utils.SmoothLimits()

        self.velocity_curve = self.velocity_history_plot.plot(
            pen=et.utils.pg_pen_cycler(0), name="Estimated velocity"
        )

        self.psd_html = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:13pt;">'
            "{}</span></div>"
        )

        self.distance_text_item = pg.TextItem(
            html=self.psd_html,
            fill=pg.mkColor(0x1F, 0x77, 0xB4, 180),
            anchor=(0.5, 0),
        )

        self.velocity_history_plot.addItem(self.distance_text_item)

        self.velocity_history = np.zeros(self.history_length_n)

        self.lower_std_history = np.zeros(self.history_length_n)
        self.upper_std_history = np.zeros(self.history_length_n)

        self.lower_std_curve = self.velocity_history_plot.plot()
        self.upper_std_curve = self.velocity_history_plot.plot()

        fbi = pg.FillBetweenItem(
            self.lower_std_curve,
            self.upper_std_curve,
            brush=pg.mkBrush(f"{et.utils.color_cycler(0)}50"),
        )

        self.velocity_history_plot.addItem(fbi)

        # PSD plot

        self.psd_plot = self._create_plot(win, row=1, col=0)
        self.psd_plot.setTitle("PSD<br>(colored area represents the slow zone)")
        self.psd_plot.setLabel(axis="left", text="Power")
        self.psd_plot.setLabel(axis="bottom", text="Velocity", units="m/s")
        self.psd_plot.addLegend(labelTextSize="10pt")

        self.psd_smooth_max = et.utils.SmoothMax(tau_grow=0.5, tau_decay=2.0)
        self.psd_curve = self.psd_plot.plot(pen=et.utils.pg_pen_cycler(0), name="PSD")
        self.psd_threshold = self.psd_plot.plot(pen=c0_dashed_pen, name="Threshold")

        psd_slow_zone_color = et.utils.color_cycler(0)
        psd_slow_zone_color = f"{psd_slow_zone_color}50"
        psd_slow_zone_brush = pg.mkBrush(psd_slow_zone_color)

        self.psd_slow_zone = pg.LinearRegionItem(brush=psd_slow_zone_brush, movable=False)
        self.psd_plot.addItem(self.psd_slow_zone)

        brush = et.utils.pg_brush_cycler(0)
        self.psd_peak_plot_item = pg.PlotDataItem(
            pen=None, symbol="o", symbolSize=8, symbolBrush=brush, symbolPen="k"
        )
        self.psd_plot.addItem(self.psd_peak_plot_item)

        self.psd_plot.setLogMode(x=False, y=True)

    def update(self, example_app_result) -> None:
        processor_extra_result = example_app_result.processor_extra_result

        lim = self.velocity_smooth_limits.update(example_app_result.velocity)

        self.velocity_history_plot.setYRange(
            lim[0] - self._VELOCITY_Y_SCALE_MARGIN_M, lim[1] + self._VELOCITY_Y_SCALE_MARGIN_M
        )
        self.velocity_history_plot.setXRange(-self.history_length_s, 0)

        xs = np.linspace(-self.history_length_s, 0, self.history_length_n)

        self.velocity_history = np.roll(self.velocity_history, -1)
        self.velocity_history[-1] = example_app_result.velocity
        self.velocity_curve.setData(xs, self.velocity_history)

        velocity_html = self.psd_html.format(
            f"Distance {np.around(example_app_result.distance_m, 2)} m"
        )
        self.distance_text_item.setHtml(velocity_html)
        self.distance_text_item.setPos(
            -self.history_length_s / 2, lim[1] + self._VELOCITY_Y_SCALE_MARGIN_M
        )

        self.lower_std_history = np.roll(self.lower_std_history, -1)
        self.lower_std_history[-1] = (
            example_app_result.velocity + 0.5 * processor_extra_result.peak_width
        )
        self.lower_std_curve.setData(xs, self.lower_std_history)

        self.upper_std_history = np.roll(self.upper_std_history, -1)
        self.upper_std_history[-1] = (
            example_app_result.velocity - 0.5 * processor_extra_result.peak_width
        )
        self.upper_std_curve.setData(xs, self.upper_std_history)

        lim = self.psd_smooth_max.update(processor_extra_result.psd)
        self.psd_plot.setYRange(np.log(0.5), np.log(lim))
        self.psd_plot.setXRange(
            processor_extra_result.max_bin_vertical_vs[0],
            processor_extra_result.max_bin_vertical_vs[-1],
        )
        self.psd_curve.setData(
            processor_extra_result.vertical_velocities, processor_extra_result.psd
        )
        self.psd_threshold.setData(
            processor_extra_result.vertical_velocities, processor_extra_result.psd_threshold
        )
        if processor_extra_result.peak_idx is not None:
            self.psd_peak_plot_item.setData(
                [processor_extra_result.vertical_velocities[processor_extra_result.peak_idx]],
                [processor_extra_result.psd[processor_extra_result.peak_idx]],
            )
        else:
            self.psd_peak_plot_item.clear()

        middle_idx = int(np.around(processor_extra_result.vertical_velocities.shape[0] / 2))
        self.psd_slow_zone.setRegion(
            [
                processor_extra_result.vertical_velocities[middle_idx - self.slow_zone],
                processor_extra_result.vertical_velocities[middle_idx + self.slow_zone],
            ]
        )

    @staticmethod
    def _create_plot(parent: pg.GraphicsLayout, row: int, col: int) -> pg.PlotItem:
        velocity_history_plot = parent.addPlot(row=row, col=col)
        velocity_history_plot.setMenuEnabled(False)
        velocity_history_plot.setMouseEnabled(x=False, y=False)
        velocity_history_plot.hideButtons()
        velocity_history_plot.showGrid(x=True, y=True, alpha=0.5)

        return velocity_history_plot


if __name__ == "__main__":
    main()
