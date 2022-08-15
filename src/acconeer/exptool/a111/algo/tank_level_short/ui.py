# Copyright (c) Acconeer AB, 2022
# All rights reserved

import pyqtgraph as pg

import acconeer.exptool as et


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.history_length_s = processing_config.history_length_s
        self.fs = sensor_config.update_rate

    def setup(self, win):
        win.setWindowTitle("Tank level short range")

        self.plot = win.addPlot()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel("bottom", "Depth (m)")
        self.plot.setLabel("left", "Amplitude")
        self.plot.setXRange(self.depths[0], self.depths[-1])
        self.text_x_pos = (self.depths[-1] - self.depths[0]) / 2 + self.depths[0]
        self.text_y_pos = 1.0

        win.nextRow()

        # Detection history Plot
        self.hist_plot = win.addPlot(title="Detected peaks")
        self.hist_plot.setMenuEnabled(False)
        self.hist_plot.setMouseEnabled(x=False, y=False)
        self.hist_plot.hideButtons()
        self.hist_plot.showGrid(x=True, y=True)
        self.hist_plot.addLegend()
        self.hist_plot.setLabel("bottom", "Time history (s)")
        self.hist_plot.setLabel("left", "Distance (mm)")
        self.hist_plot.setXRange(-self.history_length_s, 0)
        self.hist_plot.setYRange(1000.0 * self.depths[0], 1000.0 * self.depths[-1])

        self.main_peak = self.hist_plot.plot(
            pen=None,
            symbol="o",
            symbolSize=8,
            symbolPen="k",
            symbolBrush=et.utils.color_cycler(0),
            name="Main peak",
        )

        self.smooth_data = self.plot.plot(pen=et.utils.pg_pen_cycler(1))
        self.smooth_max = et.utils.SmoothMax(self.sensor_config.update_rate)

    def set_text(self, text):
        self.guess_html_format = (
            '<div style="text-align: center">'
            '<span style="color: #FFFFFF;font-size:16pt;">'
            "{}</span></div>"
        )
        guess_html = self.guess_html_format.format(text)
        self.guess_text_item = pg.TextItem(
            html=guess_html,
            fill=pg.mkColor(255, 140, 0),
            anchor=(0.5, 0),
        )

        self.guess_text_item.setPos(self.text_x_pos, self.text_y_pos)
        self.plot.addItem(self.guess_text_item)
        self.guess_text_item.setVisible(True)

    def update(self, plot_data):

        smooth_data = plot_data["smooth_data"]
        best_guess = plot_data["best_guess"]

        guess_history = plot_data["guess_hist"]
        guess_hist_indexes = plot_data["guess_hist_idx"]

        guess_str = "Best guess: {:.4f}".format(best_guess)
        self.smooth_data.setData(self.depths, smooth_data)
        x_indexes = (guess_hist_indexes - plot_data["index"]) / self.fs
        self.main_peak.setData(x_indexes, 1000 * guess_history)

        self.plot.setYRange(0.0, 1.2)
        self.set_text(guess_str)
