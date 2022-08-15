# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = et.a111.get_range_depths(sensor_config, session_info)

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        hist_s = processing_config.history_length_s
        self.hist_plot.setXRange(-hist_s, 0.06 * hist_s)

        self.limit_line.setPos(processing_config.weight_threshold)
        self.update_detection_limits()

    def setup(self, win):
        win.setWindowTitle("Acconeer Parking Detector")

        # Sweep Plot
        self.sweep_plot = win.addPlot(title="Sweep")
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.setMouseEnabled(x=False, y=False)
        self.sweep_plot.hideButtons()
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend(offset=(-10, 10))
        self.sweep_plot.setLabel("bottom", "Distance (cm)")
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setYRange(0, 2000)
        self.sweep_plot.setXRange(100.0 * self.depths[0], 100.0 * self.depths[-1])

        self.sweep_curve = self.sweep_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Envelope sweep",
        )

        self.sweep_background = self.sweep_plot.plot(
            pen=et.utils.pg_pen_cycler(2),
            name="Background estimate",
        )

        self.leak_estimate = self.sweep_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(1),
            name="Leak estimate",
        )

        # To show the legend correctly before the first update
        self.leak_estimate.setData([], [])

        self.smooth_max_sweep = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=5,
        )

        win.nextRow()

        # Reflector weight Plot
        self.weight_plot = win.addPlot(title="Reflection observables")
        self.weight_plot.setMenuEnabled(False)
        self.weight_plot.setMouseEnabled(x=False, y=False)
        self.weight_plot.hideButtons()
        self.weight_plot.showGrid(x=True, y=True)
        self.weight_plot.addLegend(offset=(-10, 10))
        self.weight_plot.setLabel("bottom", "Distance (cm)")
        self.weight_plot.setLabel("left", "Weight")
        self.weight_plot.setYRange(0, 500)
        self.weight_plot.setXRange(100.0 * self.depths[0], 100.0 * self.depths[-1])

        self.detection_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        detection_html = self.detection_html_format.format("Parked car detected!")

        self.detection_text_item = pg.TextItem(
            html=detection_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.weight_plot.addItem(self.detection_text_item)
        self.detection_text_item.hide()

        self.weight_curve = self.weight_plot.plot(
            pen=et.utils.pg_pen_cycler(0),
            name="Reflector weight",
        )

        self.limits_center = None
        self.detection_limits = self.weight_plot.plot(
            pen=et.utils.pg_pen_cycler(3),
            name="Detection limits",
        )
        self.limit_line = pg.InfiniteLine(angle=0, pen=et.utils.pg_pen_cycler(3, "--"))
        self.weight_plot.addItem(self.limit_line)

        self.trailing_sweeps = self.weight_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(2),
            name="Queued sweep",
        )

        self.current_sweep = self.weight_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(1),
            name="Last sweep",
        )

        # To show the legends correctly before the first update
        self.trailing_sweeps.setData([], [])
        self.current_sweep.setData([], [])

        self.smooth_max_weight = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            hysteresis=0.6,
            tau_decay=5,
        )

        win.nextRow()

        # Detection history Plot
        self.hist_plot = win.addPlot(title="Detection history")
        self.hist_plot.setMenuEnabled(False)
        self.hist_plot.setMouseEnabled(x=False, y=False)
        self.hist_plot.hideButtons()
        self.hist_plot.showGrid(x=True, y=False)
        self.hist_plot.hideAxis("left")
        self.hist_plot.setLabel("bottom", "Time (s)")
        self.hist_plot.setYRange(-0.5, 1.5)
        self.true_text_item = pg.TextItem("True", color=pg.mkColor(0, 0, 0), anchor=(0, 0.5))
        self.true_text_item.setPos(0.01 * self.processing_config.history_length_s, 1)
        self.false_text_item = pg.TextItem("False", color=pg.mkColor(0, 0, 0), anchor=(0, 0.5))
        self.false_text_item.setPos(0.01 * self.processing_config.history_length_s, 0)
        self.hist_plot.addItem(self.true_text_item)
        self.hist_plot.addItem(self.false_text_item)

        self.hist_dots = self.hist_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=5,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(0),
        )

        win.layout.setRowStretchFactor(0, 8)
        win.layout.setRowStretchFactor(1, 9)

        self.update_processing_config()

    def update_detection_limits(self):
        if self.limits_center is not None:
            pc = self.processing_config
            criterion_weight_min = self.limits_center[0] / np.sqrt(pc.weight_ratio_limit)
            if criterion_weight_min < pc.weight_threshold:
                criterion_weight_min = pc.weight_threshold
            criterion_weight_max = criterion_weight_min * pc.weight_ratio_limit

            criterion_distance_min = self.limits_center[1] - pc.distance_difference_limit / 2
            criterion_distance_max = criterion_distance_min + pc.distance_difference_limit

            weight_limits = [
                criterion_weight_max,
                criterion_weight_max,
                criterion_weight_min,
                criterion_weight_min,
            ]
            distance_limits = [
                criterion_distance_max,
                criterion_distance_min,
                criterion_distance_min,
                criterion_distance_max,
            ]

            weight_limits.append(weight_limits[0])
            distance_limits.append(distance_limits[0])

            weight_limits = np.array(weight_limits)
            distance_limits = np.array(distance_limits)

            self.detection_limits.setData(100.0 * distance_limits, weight_limits)

    def update(self, data):
        self.sweep_curve.setData(100.0 * self.depths, data["sweep"])
        self.leak_estimate.setData(100.0 * data["leak_estimate_depths"], data["leak_estimate"])
        self.sweep_background.setData(100.0 * self.depths, data["background"])
        self.weight_curve.setData(100.0 * self.depths, data["weight"])
        self.limits_center = data["limits_center"]
        self.update_detection_limits()
        self.trailing_sweeps.setData(
            100.0 * data["queued_distances"][:-1], data["queued_weights"][:-1]
        )
        self.current_sweep.setData(
            100.0 * data["queued_distances"][-1:], data["queued_weights"][-1:]
        )
        self.hist_dots.setData(data["detection_history_t"], data["detection_history"])

        ymax = self.smooth_max_sweep.update(np.nanmax(data["sweep"]))
        self.sweep_plot.setYRange(0, ymax)

        ymax = self.smooth_max_weight.update(
            np.nanmax(np.append(data["weight"], data["queued_weights"]))
        )
        self.weight_plot.setYRange(0, ymax)
        xmid = (self.depths[0] + self.depths[-1]) / 2
        self.detection_text_item.setPos(100.0 * xmid, 0.95 * ymax)
        self.detection_text_item.setVisible(bool(data["detection_history"][-1]))
