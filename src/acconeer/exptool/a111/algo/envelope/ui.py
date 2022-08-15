# Copyright (c) Acconeer AB, 2022
# All rights reserved

from PySide6 import QtGui

import pyqtgraph as pg

import acconeer.exptool as et

from ._processor import ProcessingConfiguration


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.depth_res = session_info["step_length_m"]
        self.smooth_max = et.utils.SmoothMax(sensor_config.update_rate)

        self.setup_is_done = False

    def setup(self, win):
        num_sensors = len(self.sensor_config.sensor)

        self.ampl_plot = win.addPlot(row=0, colspan=num_sensors)
        self.ampl_plot.setMenuEnabled(False)
        self.ampl_plot.setMouseEnabled(x=False, y=False)
        self.ampl_plot.hideButtons()
        self.ampl_plot.showGrid(x=True, y=True)
        self.ampl_plot.setLabel("bottom", "Depth (m)")
        self.ampl_plot.setLabel("left", "Amplitude")
        self.ampl_plot.setXRange(*self.depths.take((0, -1)))
        self.ampl_plot.setYRange(0, 1)  # To avoid rendering bug
        self.ampl_plot.addLegend(offset=(-10, 10))

        self.ampl_curves = []
        self.bg_curves = []
        self.peak_lines = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            legend = "Sensor {}".format(sensor_id)
            ampl_curve = self.ampl_plot.plot(pen=et.utils.pg_pen_cycler(i), name=legend)
            bg_curve = self.ampl_plot.plot(pen=et.utils.pg_pen_cycler(i, style="--"))
            color_tuple = et.utils.hex_to_rgb_tuple(et.utils.color_cycler(i))
            peak_line = pg.InfiniteLine(pen=pg.mkPen(pg.mkColor(*color_tuple, 150), width=2))
            self.ampl_plot.addItem(peak_line)
            self.ampl_curves.append(ampl_curve)
            self.bg_curves.append(bg_curve)
            self.peak_lines.append(peak_line)

        bg = pg.mkColor(0xFF, 0xFF, 0xFF, 150)
        self.peak_text = pg.TextItem(anchor=(0, 1), color="k", fill=bg)
        self.peak_text.setPos(self.depths[0], 0)
        self.peak_text.setZValue(100)
        self.ampl_plot.addItem(self.peak_text)

        rate = self.sensor_config.update_rate
        xlabel = "Sweeps" if rate is None else "Time (s)"
        x_scale = 1.0 if rate is None else 1.0 / rate
        y_scale = self.depth_res
        x_offset = -self.processing_config.history_length * x_scale
        y_offset = self.depths[0] - 0.5 * self.depth_res
        is_single_sensor = len(self.sensor_config.sensor) == 1

        self.history_plots = []
        self.history_ims = []
        for i, sensor_id in enumerate(self.sensor_config.sensor):
            title = None if is_single_sensor else "Sensor {}".format(sensor_id)
            plot = win.addPlot(row=1, col=i, title=title)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.hideButtons()
            plot.setLabel("bottom", xlabel)
            plot.setLabel("left", "Depth (m)")
            im = pg.ImageItem(autoDownsample=True)
            im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
            im.resetTransform()
            tr = QtGui.QTransform()
            tr.translate(x_offset, y_offset)
            tr.scale(x_scale, y_scale)
            im.setTransform(tr)
            plot.addItem(im)
            self.history_plots.append(plot)
            self.history_ims.append(im)

        self.setup_is_done = True
        self.update_processing_config()

    def update_processing_config(self, processing_config=None):
        if processing_config is None:
            processing_config = self.processing_config
        else:
            self.processing_config = processing_config

        if not self.setup_is_done:
            return

        self.show_peaks = processing_config.show_peak_depths
        self.peak_text.setVisible(self.show_peaks)

        show_bg = processing_config.bg_mode == ProcessingConfiguration.BackgroundMode.LIMIT

        for curve in self.bg_curves:
            curve.setVisible(show_bg)

    def update(self, d):
        sweeps = d["output_data"]
        bgs = d["bg"]
        histories = d["history"]

        for i, _ in enumerate(self.sensor_config.sensor):
            self.ampl_curves[i].setData(self.depths, sweeps[i])

            if bgs is None:
                self.bg_curves[i].clear()
            else:
                self.bg_curves[i].setData(self.depths, bgs[i])

            peak = d["peak_depths"][i]
            if peak is not None and self.show_peaks:
                self.peak_lines[i].setPos(peak)
                self.peak_lines[i].show()
            else:
                self.peak_lines[i].hide()

            im = self.history_ims[i]
            history = histories[:, i]
            im.updateImage(history, levels=(0, 1.05 * history.max()))

        m = self.smooth_max.update(sweeps.max())
        self.ampl_plot.setYRange(0, m)

        # Update peak text item
        val_strs = ["-" if p is None else "{:5.3f} m".format(p) for p in d["peak_depths"]]
        z = zip(self.sensor_config.sensor, val_strs)
        t = "\n".join(["Sensor {}: {}".format(sid, v) for sid, v in z])
        self.peak_text.setText(t)
