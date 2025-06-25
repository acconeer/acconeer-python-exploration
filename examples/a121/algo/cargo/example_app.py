# Copyright (c) Acconeer AB, 2025
# All rights reserved

from __future__ import annotations

import numpy as np

# Added here to force pyqtgraph to choose PySide
import PySide6  # noqa: F401
from PySide6.QtGui import QFont

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo.cargo import (
    CargoPresenceConfig,
    ExApp,
    ExAppConfig,
    ExAppContext,
    ExAppResult,
    UtilizationLevelConfig,
)

# These are some of the presets available.
# Replace 'ex_app_config' further down to use one of the presets
from acconeer.exptool.a121.algo.cargo._configs import (
    get_10_ft_container_config,
    get_20_ft_container_config,
    get_40_ft_container_config,
)
from acconeer.exptool.a121.algo.cargo._ex_app import PRESENCE_RUN_TIME_S, ContainerSize, _Mode


SENSOR_ID = 1


def main():
    args = a121.ExampleArgumentParser().parse_args()
    et.utils.config_logging(args)

    client = a121.Client.open(**a121.get_client_args(args))

    # All configurable parameters are displayed here.
    # These settings correspond to the "No lens" preset.
    # There are also other preset configurations available by the imports!

    utilization_level_config = UtilizationLevelConfig(
        update_rate=5,
        threshold_sensitivity=0.5,
        signal_quality=25,
    )

    cargo_presence_config = CargoPresenceConfig(
        burst_rate=0.1,
        update_rate=6,
        signal_quality=30,
        sweeps_per_frame=12,
        inter_detection_threshold=2,
        intra_detection_threshold=2,
    )

    ex_app_config = ExAppConfig(
        activate_presence=True,
        cargo_presence_config=cargo_presence_config,
        activate_utilization_level=True,
        utilization_level_config=utilization_level_config,
        container_size=ContainerSize.CONTAINER_20_FT,
    )

    example_app = ExApp(
        client=client,
        sensor_id=SENSOR_ID,
        ex_app_config=ex_app_config,
    )
    example_app.start()

    pg_updater = PGUpdater(
        ex_app_config,
        example_app.ex_app_context,
    )

    pg_process = et.PGProcess(pg_updater)
    pg_process.start()

    interrupt_handler = et.utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    while not interrupt_handler.got_signal:
        example_app_result = example_app.get_next()
        if example_app_result.mode == _Mode.DISTANCE:
            if example_app_result.level_m is not None:
                result_str = (
                    f"Utilization level: {np.around(example_app_result.level_m, 2)} m, "
                    f"{int(np.around(example_app_result.level_percent, 0))}%"
                )
            else:
                result_str = "No utilization level detected"
        else:
            if example_app_result.presence_detected:
                result_str = "Presence detected"
            else:
                result_str = "Presence not detected"
        print(f"Running detector: {example_app_result.mode.name}\n" f"{result_str}\n")

        try:
            pg_process.put_data(example_app_result)
        except et.PGProccessDiedException:
            break

    print("Disconnecting...")
    pg_process.close()
    client.close()


class PGUpdater:
    def __init__(self, ex_app_config: ExAppConfig, ex_app_context: ExAppContext):
        self.ex_app_config = ex_app_config
        self.ex_app_context = ex_app_context

    def setup(self, win) -> None:
        self.utilization_level_config = self.ex_app_config.utilization_level_config
        self.cargo_presence_config = self.ex_app_config.cargo_presence_config

        self.num_rects = 16

        # Utilization level

        if self.ex_app_config.activate_utilization_level:
            # Distance sweep plot

            self.sweep_plot = win.addPlot(row=0, col=0, title="Distance sweep")
            self.sweep_plot.setMenuEnabled(False)
            self.sweep_plot.showGrid(x=True, y=True)
            self.sweep_plot.addLegend()
            self.sweep_plot.setLabel("left", "Amplitude")
            self.sweep_plot.setLabel("bottom", "Distance (m)")
            self.sweep_plot.addItem(pg.PlotDataItem())

            self.num_curves = 4

            pen = et.utils.pg_pen_cycler(0)
            brush = et.utils.pg_brush_cycler(0)
            symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
            feat_kw = dict(pen=pen, **symbol_kw)
            self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

            pen = et.utils.pg_pen_cycler(1)
            brush = et.utils.pg_brush_cycler(1)
            symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
            feat_kw = dict(pen=pen, **symbol_kw)
            self.threshold_curves = [
                self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)
            ]

            sweep_plot_legend = pg.LegendItem(offset=(-30, 30))
            sweep_plot_legend.setParentItem(self.sweep_plot.graphicsItem())
            sweep_plot_legend.addItem(self.sweep_curves[0], "Sweep")
            sweep_plot_legend.addItem(self.threshold_curves[0], "Threshold")

            font = QFont()
            font.setPixelSize(16)
            self.sweep_text_item = pg.TextItem(
                fill=pg.mkColor(0xFF, 0x7F, 0x0E, 200),
                anchor=(0.5, 0),
                color=pg.mkColor(0xFF, 0xFF, 0xFF, 200),
            )
            self.sweep_text_item.setFont(font)
            self.sweep_text_item.hide()
            self.sweep_plot.addItem(self.sweep_text_item)

            self.sweep_main_peak_line = pg.InfiniteLine(pen=pg.mkPen("k", width=1.5, dash=[2, 8]))
            self.sweep_main_peak_line.hide()
            self.sweep_plot.addItem(self.sweep_main_peak_line)

            self.sweep_smooth_max = et.utils.SmoothMax()

            # Utilization level plot

            self.rect_plot = win.addPlot(row=1, col=0, title="Utilization level")
            self.rect_plot.setAspectLocked()
            self.rect_plot.hideAxis("left")
            self.rect_plot.hideAxis("bottom")
            self.rects = []

            pen = pg.mkPen(None)
            rect_height = self.num_rects / 2.0
            for r in np.arange(self.num_rects) + 1:
                rect = pg.QtWidgets.QGraphicsRectItem(r, rect_height, 1, rect_height)
                rect.setPen(pen)
                rect.setBrush(et.utils.pg_brush_cycler(7))
                self.rect_plot.addItem(rect)
                self.rects.append(rect)

            self.level_html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>"
            )

            self.level_text_item = pg.TextItem(
                fill=pg.mkColor(0, 150, 0),
                anchor=(0.5, 0),
            )

            no_detection_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("No level detected")
            )

            self.no_detection_text_item = pg.TextItem(
                html=no_detection_html,
                fill=pg.mkColor("r"),
                anchor=(0.5, 0),
            )

            self.rect_plot.addItem(self.level_text_item)
            self.rect_plot.addItem(self.no_detection_text_item)
            self.level_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.level_text_item.hide()
            self.no_detection_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.no_detection_text_item.show()

        # Presence

        if self.ex_app_config.activate_presence:
            estimated_frame_rate = self.ex_app_context.presence_context.estimated_frame_rate

            self.history_length_n = int(round(PRESENCE_RUN_TIME_S * estimated_frame_rate) + 1)
            self.intra_history = np.zeros(self.history_length_n)
            self.inter_history = np.zeros(self.history_length_n)

            # Presence history plot

            self.presence_hist_plot = win.addPlot(
                row=0,
                col=1,
                title="Presence history",
            )
            self.presence_hist_plot.setMenuEnabled(False)
            self.presence_hist_plot.setMouseEnabled(x=False, y=False)
            self.presence_hist_plot.hideButtons()
            self.presence_hist_plot.showGrid(x=True, y=True)
            self.presence_hist_plot.setLabel("bottom", "Time (s)")
            self.presence_hist_plot.setLabel("left", "Score")
            self.presence_hist_plot.setXRange(-PRESENCE_RUN_TIME_S, 0)
            self.presence_history_smooth_max = et.utils.SmoothMax(estimated_frame_rate)
            self.presence_hist_plot.setYRange(0, 10)

            self.intra_dashed_pen = et.utils.pg_pen_cycler(1, width=2.5, style="--")
            self.intra_pen = et.utils.pg_pen_cycler(1)

            self.intra_hist_curve = self.presence_hist_plot.plot(pen=self.intra_pen)
            self.intra_limit_line = pg.InfiniteLine(angle=0, pen=self.intra_dashed_pen)
            self.presence_hist_plot.addItem(self.intra_limit_line)
            self.intra_limit_line.setPos(self.cargo_presence_config.intra_detection_threshold)
            self.intra_limit_line.setPen(self.intra_dashed_pen)

            self.inter_pen = et.utils.pg_pen_cycler(0)
            self.inter_dashed_pen = et.utils.pg_pen_cycler(0, width=2.5, style="--")

            self.inter_hist_curve = self.presence_hist_plot.plot(pen=self.inter_pen)
            self.inter_limit_line = pg.InfiniteLine(angle=0, pen=self.inter_dashed_pen)
            self.presence_hist_plot.addItem(self.inter_limit_line)
            self.inter_limit_line.setPos(self.cargo_presence_config.inter_detection_threshold)
            self.inter_limit_line.setPen(self.inter_dashed_pen)

            self.hist_xs = np.linspace(-PRESENCE_RUN_TIME_S, 0, self.history_length_n)

            # Presence detection plot

            self.presence_detection_plot = win.addPlot(row=1, col=1, title="Presence")
            self.presence_detection_plot.setAspectLocked()
            self.presence_detection_plot.hideAxis("left")
            self.presence_detection_plot.hideAxis("bottom")

            present_html_format = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("Presence detected")
            )
            not_present_html = (
                '<div style="text-align: center">'
                '<span style="color: #FFFFFF;font-size:12pt;">'
                "{}</span></div>".format("No presence detected")
            )
            self.present_text_item = pg.TextItem(
                html=present_html_format,
                fill=pg.mkColor(0, 150, 0),
                anchor=(0.65, 0),
            )
            self.not_present_text_item = pg.TextItem(
                html=not_present_html,
                fill=pg.mkColor("r"),
                anchor=(0.6, 0),
            )

            self.presence_detection_plot.addItem(self.present_text_item)
            self.presence_detection_plot.addItem(self.not_present_text_item)
            self.present_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.not_present_text_item.setPos(self.num_rects / 2.0 + 1, self.num_rects + 2)
            self.present_text_item.hide()

            pen = pg.mkPen(None)
            rect_height = self.num_rects / 2.0
            rect_length = self.num_rects

            self.presence_rect = pg.QtWidgets.QGraphicsRectItem(
                0, rect_height, rect_length, rect_height
            )
            self.presence_rect.setPen(pen)
            self.presence_rect.setBrush(et.utils.pg_brush_cycler(7))
            self.presence_detection_plot.addItem(self.presence_rect)

    def update(self, result: ExAppResult) -> None:
        if result.mode == _Mode.DISTANCE:
            if self.ex_app_config.activate_presence:
                self.intra_history = np.zeros(self.history_length_n)
                self.inter_history = np.zeros(self.history_length_n)

            # Sweep plot

            distance = result.distance
            max_val_in_plot = 0
            if result.distance_processor_result is not None:
                for idx, processor_result in enumerate(result.distance_processor_result):
                    abs_sweep = processor_result.extra_result.abs_sweep
                    threshold = processor_result.extra_result.used_threshold
                    distances_m = processor_result.extra_result.distances_m

                    self.sweep_curves[idx].setData(distances_m, abs_sweep)
                    self.threshold_curves[idx].setData(distances_m, threshold)

                    max_val_in_subsweep = max(max(threshold), max(abs_sweep))
                    if max_val_in_plot < max_val_in_subsweep:
                        max_val_in_plot = max_val_in_subsweep

                self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_plot))

            if distance is not None:
                text_y_pos = self.sweep_plot.getAxis("left").range[1] * 0.95
                text_x_pos = (
                    self.sweep_plot.getAxis("bottom").range[1]
                    + self.sweep_plot.getAxis("bottom").range[0]
                ) / 2.0
                self.sweep_text_item.setPos(text_x_pos, text_y_pos)
                self.sweep_text_item.setHtml("Main peak distance: {:.3f} m".format(distance))
                self.sweep_text_item.show()

                self.sweep_main_peak_line.setPos(distance)
                self.sweep_main_peak_line.show()
            else:
                self.sweep_text_item.hide()
                self.sweep_main_peak_line.hide()

            # Utilization level plot

            # Show the percentage level plot if the plot width is greater than 400 pixels,
            # otherwise display the level as text.

            if result.level_percent is None:  # No detection
                for rect in self.rects:
                    rect.setBrush(et.utils.pg_brush_cycler(7))
                self.level_text_item.hide()
                self.no_detection_text_item.show()
            else:
                self.bar_loc = int(
                    np.around(self.num_rects - result.level_percent / 100 * self.num_rects)
                )
                for rect in self.rects[self.bar_loc :]:
                    rect.setBrush(et.utils.pg_brush_cycler(0))

                for rect in self.rects[: self.bar_loc]:
                    rect.setBrush(et.utils.pg_brush_cycler(7))

                level_text = "Utilization level: {:.2f} m, {:.0f} %".format(
                    result.level_m,
                    result.level_percent,
                )
                level_html = self.level_html_format.format(level_text)
                self.level_text_item.setHtml(level_html)
                self.level_text_item.show()
                self.no_detection_text_item.hide()

            for rect in self.rects:
                rect.setVisible(True)

        else:
            # Presence history

            self.intra_history = np.roll(self.intra_history, -1)
            self.intra_history[-1] = result.intra_presence_score
            self.intra_hist_curve.setData(self.hist_xs, self.intra_history)

            self.inter_history = np.roll(self.inter_history, -1)
            self.inter_history[-1] = result.inter_presence_score
            self.inter_hist_curve.setData(self.hist_xs, self.inter_history)

            # Set y-range

            if np.isnan(self.intra_history).all():
                intra_m_hist = self.cargo_presence_config.intra_detection_threshold
            else:
                intra_m_hist = max(
                    float(np.nanmax(self.intra_history)),
                    self.cargo_presence_config.intra_detection_threshold * 1.05,
                )

            if np.isnan(self.inter_history).all():
                inter_m_hist = self.cargo_presence_config.inter_detection_threshold
            else:
                inter_m_hist = max(
                    float(np.nanmax(self.inter_history)),
                    self.cargo_presence_config.inter_detection_threshold * 1.05,
                )

            m_hist = max(intra_m_hist, inter_m_hist)
            m_hist = self.presence_history_smooth_max.update(m_hist)
            self.presence_hist_plot.setYRange(0, m_hist)

            # Presence detection plot

            if result.presence_detected:
                self.present_text_item.show()
                self.not_present_text_item.hide()
                self.presence_rect.setBrush(pg.mkColor(0, 150, 0))
            else:
                self.present_text_item.hide()
                self.not_present_text_item.show()
                self.presence_rect.setBrush(et.utils.pg_brush_cycler(7))


if __name__ == "__main__":
    main()
