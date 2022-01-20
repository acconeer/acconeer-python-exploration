import logging

import numpy as np
import pyqtgraph as pg
from numpy import unravel_index
from pyqtgraph.Qt import QtGui

from PyQt5 import QtCore

import acconeer.exptool as et

from .constants import FUSION_HISTORY, FUSION_MAX_OBSTACLES, FUSION_MAX_SHADOWS, WAVELENGTH


log = logging.getLogger("acconeer.exptool.examples.obstacle_detection")


class PGUpdater:
    def __init__(self, sensor_config, processing_config, session_info):
        self.sensor_config = sensor_config
        self.map_max = 0
        self.width = 3
        self.max_velocity = WAVELENGTH / 4 * self.sensor_config.update_rate  # cm/s
        self.peak_hist_len = processing_config["peak_hist"]["value"]
        self.dist_index = processing_config["downsampling"]["value"]
        self.nr_locals = processing_config["nr_peaks"]["value"]
        self.downsampling = processing_config["downsampling"]["value"]
        self.threshold = processing_config["static_threshold"]["value"]
        self.sensor_separation = processing_config["sensor_separation"]["value"]
        self.fusion_max_obstacles = FUSION_MAX_OBSTACLES
        self.fusion_max_shadows = FUSION_MAX_SHADOWS
        self.fusion_history = FUSION_HISTORY
        self.fft_bg_data = None
        self.threshold_data = None

        self.hist_plots = {
            "velocity": [[], processing_config["velocity_history"]["value"]],
            "angle": [[], processing_config["angle_history"]["value"]],
            "distance": [[], processing_config["distance_history"]["value"]],
            "amplitude": [[], processing_config["amplitude_history"]["value"]],
        }
        self.num_hist_plots = 0
        for hist in self.hist_plots:
            if hist[1]:
                self.num_hist_plots += 1
        self.advanced_plots = {
            "background_map": processing_config["background_map"]["value"],
            "threshold_map": processing_config["threshold_map"]["value"],
            "show_line_outs": processing_config["show_line_outs"]["value"],
            "fusion_map": processing_config["fusion_map"]["value"],
            "show_shadows": False,
        }

        if self.advanced_plots["fusion_map"] and len(sensor_config.sensor) > 2:
            self.advanced_plots["fusion_map"] = False
            log.warning("Sensor fusion needs 2 sensors!")
        if self.advanced_plots["fusion_map"] and len(sensor_config.sensor) == 1:
            log.warning("Sensor fusion needs 2 sensors! Plotting single sensor data.")

        if self.advanced_plots["fusion_map"]:
            self.advanced_plots["show_shadows"] = processing_config["show_shadows"]["value"]

    def setup(self, win):
        win.setWindowTitle("Acconeer obstacle detection example")

        row_idx = 0
        self.env_ax = win.addPlot(row=row_idx, col=0, colspan=4, title="Envelope and max FFT")
        self.env_ax.setMenuEnabled(False)
        self.env_ax.setMouseEnabled(x=False, y=False)
        self.env_ax.hideButtons()
        self.env_ax.setLabel("bottom", "Depth (cm)")
        self.env_ax.setXRange(*(self.sensor_config.range_interval * 100))
        self.env_ax.showGrid(True, True)
        self.env_ax.addLegend(offset=(-10, 10))
        self.env_ax.setYRange(0, 0.1)

        self.env_ampl = self.env_ax.plot(pen=et.utils.pg_pen_cycler(0), name="Envelope")
        self.fft_max = self.env_ax.plot(pen=et.utils.pg_pen_cycler(1, "--"), name="FFT @ max")

        if self.advanced_plots["show_line_outs"]:
            self.fft_bg = self.env_ax.plot(pen=et.utils.pg_pen_cycler(2, "--"), name="BG @ max")
            self.fft_thresh = self.env_ax.plot(
                pen=et.utils.pg_pen_cycler(3, "--"), name="Threshold @ max"
            )

        self.peak_dist_text = pg.TextItem(color="k", anchor=(0, 1))
        self.env_ax.addItem(self.peak_dist_text)
        self.peak_dist_text.setPos(self.sensor_config.range_start * 100, 0)
        self.peak_dist_text.setZValue(3)

        self.env_peak_vline = pg.InfiniteLine(
            pos=0, angle=90, pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine)
        )
        self.env_ax.addItem(self.env_peak_vline)
        row_idx += 1

        self.obstacle_ax = win.addPlot(
            row=row_idx, col=0, colspan=self.num_hist_plots, title="Obstacle map"
        )
        self.obstacle_ax.setMenuEnabled(False)
        self.obstacle_ax.setMouseEnabled(x=False, y=False)
        self.obstacle_ax.hideButtons()
        self.obstacle_im = pg.ImageItem()
        self.obstacle_ax.setLabel("bottom", "Velocity (cm/s)")
        self.obstacle_ax.setLabel("left", "Distance (cm)")
        self.obstacle_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        self.obstacle_ax.addItem(self.obstacle_im)

        self.obstacle_ax.setXRange(-self.max_velocity, self.max_velocity)
        self.obstacle_ax.setYRange(*self.sensor_config.range_interval * 100)

        self.obstacle_ax.setXRange(-self.max_velocity, self.max_velocity)
        self.obstacle_ax.setYRange(*self.sensor_config.range_interval * 100)

        self.obstacle_peak = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.obstacle_ax.addItem(self.obstacle_peak)

        self.peak_fft_text = pg.TextItem(color="w", anchor=(0, 1))
        self.obstacle_ax.addItem(self.peak_fft_text)
        self.peak_fft_text.setPos(-self.max_velocity, self.sensor_config.range_start * 100)

        self.peak_val_text = pg.TextItem(color="w", anchor=(0, 0))
        self.obstacle_ax.addItem(self.peak_val_text)
        self.peak_val_text.setPos(-self.max_velocity, self.sensor_config.range_end * 100)

        self.bg_estimation_text = pg.TextItem(color="w", anchor=(0, 1))
        self.obstacle_ax.addItem(self.bg_estimation_text)
        self.bg_estimation_text.setPos(-self.max_velocity, self.sensor_config.range_start * 100)

        row_idx += 1
        if self.advanced_plots["background_map"]:
            self.obstacle_bg_ax = win.addPlot(
                row=row_idx, col=0, colspan=self.num_hist_plots, title="Obstacle background"
            )
            self.obstacle_bg_ax.setMenuEnabled(False)
            self.obstacle_bg_ax.setMouseEnabled(x=False, y=False)
            self.obstacle_bg_ax.hideButtons()
            self.obstacle_bg_im = pg.ImageItem()
            self.obstacle_bg_ax.setLabel("bottom", "Velocity (cm/s)")
            self.obstacle_bg_ax.setLabel("left", "Distance (cm)")
            self.obstacle_bg_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
            self.obstacle_bg_ax.addItem(self.obstacle_bg_im)
            row_idx += 1

        if self.advanced_plots["threshold_map"]:
            self.obstacle_thresh_ax = win.addPlot(
                row=row_idx, col=0, colspan=self.num_hist_plots, title="Obstacle threshold"
            )
            self.obstacle_thresh_ax.setMenuEnabled(False)
            self.obstacle_thresh_ax.setMouseEnabled(x=False, y=False)
            self.obstacle_thresh_ax.hideButtons()
            self.obstacle_thresh_im = pg.ImageItem()
            self.obstacle_thresh_ax.setLabel("bottom", "Velocity (cm/s)")
            self.obstacle_thresh_ax.setLabel("left", "Distance (cm)")
            self.obstacle_thresh_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
            self.obstacle_thresh_ax.addItem(self.obstacle_thresh_im)
            row_idx += 1

        if self.advanced_plots["fusion_map"]:
            b = et.utils.color_cycler(0)
            r = et.utils.color_cycler(1)
            p = et.utils.color_cycler(4)
            spos = self.sensor_separation / 2
            pos0 = self.sensor_config.range_start * 100
            pos1 = self.sensor_config.range_end * 100
            self.fusion_ax = win.addPlot(
                row=row_idx,
                col=0,
                colspan=self.num_hist_plots,
                title="Fused obstacle map",
            )
            self.fusion_ax.setMenuEnabled(False)
            self.fusion_ax.setMouseEnabled(x=False, y=False)
            self.fusion_ax.hideButtons()
            self.fusion_legend = self.fusion_ax.addLegend()
            self.fusion_ax.showGrid(True, True)
            self.fusion_ax.setLabel("bottom", "X (cm)")
            self.fusion_ax.setLabel("left", "Y (cm)")
            self.fusion_ax.setXRange(-pos0, pos0)
            self.fusion_ax.setYRange(pos0 - 10, pos1)

            # Add plots for fused obstacles
            self.fusion_scatter = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=10)
            self.fusion_legend.addItem(self.fusion_scatter, "Fused")
            self.fusion_ax.addItem(self.fusion_scatter)
            self.fusion_scatter.setZValue(10)
            self.fusion_hist = []
            for i in range(self.fusion_max_obstacles):
                self.fusion_hist.append(self.fusion_ax.plot(pen=et.utils.pg_pen_cycler(2, "--")))
                self.fusion_ax.addItem(self.fusion_hist[i])
                self.fusion_hist[i].setZValue(10)

            # Add plots for shadow obstacles
            if self.advanced_plots["show_shadows"]:
                self.left_sensor_shadows = pg.ScatterPlotItem(brush=pg.mkBrush(r), size=10)
                self.right_sensor_shadows = pg.ScatterPlotItem(brush=pg.mkBrush(b), size=10)
                self.fusion_ax.addItem(self.left_sensor_shadows)
                self.fusion_ax.addItem(self.right_sensor_shadows)
                self.fusion_left_shadow_hist = []
                self.fusion_right_shadow_hist = []
                for i in range(self.fusion_max_shadows):
                    self.fusion_left_shadow_hist.append(
                        self.fusion_ax.plot(pen=et.utils.pg_pen_cycler(0, "--"))
                    )
                    self.fusion_right_shadow_hist.append(
                        self.fusion_ax.plot(pen=et.utils.pg_pen_cycler(1, "--"))
                    )
                    self.fusion_ax.addItem(self.fusion_left_shadow_hist[i])
                    self.fusion_ax.addItem(self.fusion_right_shadow_hist[i])

            self.left_sensor = pg.InfiniteLine(
                pos=-spos,
                angle=90,
                pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine),
            )
            self.right_sensor = pg.InfiniteLine(
                pos=spos,
                angle=90,
                pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine),
            )
            self.detection_limit = pg.InfiniteLine(
                pos=self.sensor_config.range_start * 100,
                angle=0,
                pen=pg.mkPen(color=p, width=2, style=QtCore.Qt.DotLine),
            )
            self.fusion_ax.addItem(self.left_sensor)
            self.fusion_ax.addItem(self.right_sensor)
            self.fusion_ax.addItem(self.detection_limit)
            self.right_sensor_rect = pg.QtGui.QGraphicsRectItem(spos - 1, pos0 - 1, 2, 2)
            self.right_sensor_rect.setPen(pg.mkPen(None))
            self.right_sensor_rect.setBrush(pg.mkBrush(b))
            self.fusion_ax.addItem(self.right_sensor_rect)

            self.left_sensor_rect = pg.QtGui.QGraphicsRectItem(-spos - 1, pos0 - 1, 2, 2)
            self.left_sensor_rect.setPen(pg.mkPen(None))
            self.left_sensor_rect.setBrush(pg.mkBrush(r))
            self.fusion_ax.addItem(self.left_sensor_rect)

            id1 = self.sensor_config.sensor[0]
            if len(self.sensor_config.sensor) == 2:
                id2 = self.sensor_config.sensor[1]
            else:
                id2 = -1
            self.right_sensor_text = pg.TextItem("Sensor {}".format(id1), color=b, anchor=(0, 1))
            self.left_sensor_text = pg.TextItem("Sensor {}".format(id2), color=r, anchor=(1, 1))
            self.fusion_ax.addItem(self.left_sensor_text)
            self.fusion_ax.addItem(self.right_sensor_text)
            self.left_sensor_text.setPos(-spos, spos)
            self.right_sensor_text.setPos(spos, spos)

            if id2 == -1:
                self.left_sensor_text.hide()
                self.left_sensor_rect.hide()

            row_idx += 1

        hist_col = 0
        row_idx += self.num_hist_plots
        if self.hist_plots["distance"][1]:
            self.peak_hist_ax_l = win.addPlot(row=row_idx, col=hist_col, title="Distance history")
            self.peak_hist_ax_l.setMenuEnabled(False)
            self.peak_hist_ax_l.setMouseEnabled(x=False, y=False)
            self.peak_hist_ax_l.hideButtons()
            self.peak_hist_ax_l.setLabel("bottom", "Sweep")
            self.peak_hist_ax_l.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_l.showGrid(True, True)
            self.peak_hist_ax_l.addLegend(offset=(-10, 10))
            self.peak_hist_ax_l.setYRange(
                self.sensor_config.range_start * 100, self.sensor_config.range_end * 100
            )
            hist_col += 1

        if self.hist_plots["velocity"][1]:
            self.peak_hist_ax_c = win.addPlot(row=row_idx, col=hist_col, title="Velocity history")
            self.peak_hist_ax_c.setMenuEnabled(False)
            self.peak_hist_ax_c.setMouseEnabled(x=False, y=False)
            self.peak_hist_ax_c.hideButtons()
            self.peak_hist_ax_c.setLabel("bottom", "Sweep")
            self.peak_hist_ax_c.setXRange(0, self.peak_hist_len)
            limit = np.round(self.max_velocity / 10) * 10
            if limit < 1.0:
                limit = self.max_velocity
            self.peak_hist_ax_c.setYRange(-limit, limit)
            self.peak_hist_ax_c.showGrid(True, True)
            self.peak_hist_ax_c.addLegend(offset=(-10, 10))
            hist_col += 1

        if self.hist_plots["angle"][1]:
            self.peak_hist_ax_r = win.addPlot(row=row_idx, col=hist_col, title="Angle history")
            self.peak_hist_ax_r.setMenuEnabled(False)
            self.peak_hist_ax_r.setMouseEnabled(x=False, y=False)
            self.peak_hist_ax_r.hideButtons()
            self.peak_hist_ax_r.setLabel("bottom", "Sweep")
            self.peak_hist_ax_r.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_r.showGrid(True, True)
            self.peak_hist_ax_r.addLegend(offset=(-10, 10))
            self.peak_hist_ax_r.setYRange(-100, 100)
            hist_col += 1

        if self.hist_plots["amplitude"][1]:
            self.peak_hist_ax_r1 = win.addPlot(
                row=row_idx, col=hist_col, title="Amplitude history"
            )
            self.peak_hist_ax_r1.setMenuEnabled(False)
            self.peak_hist_ax_r1.setMouseEnabled(x=False, y=False)
            self.peak_hist_ax_r1.hideButtons()
            self.peak_hist_ax_r1.setLabel("bottom", "Sweep")
            self.peak_hist_ax_r1.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_r1.showGrid(True, True)
            self.peak_hist_ax_r1.addLegend(offset=(-10, 10))
            hist_col += 1

        for i in range(self.nr_locals):
            if self.hist_plots["velocity"][1]:
                self.hist_plots["velocity"][0].append(
                    self.peak_hist_ax_c.plot(
                        pen=et.utils.pg_pen_cycler(i), name="Veloctiy {:d}".format(i)
                    )
                )
            if self.hist_plots["angle"][1]:
                self.hist_plots["angle"][0].append(
                    self.peak_hist_ax_r.plot(
                        pen=et.utils.pg_pen_cycler(i), name="Angle {:d}".format(i)
                    )
                )
            if self.hist_plots["distance"][1]:
                self.hist_plots["distance"][0].append(
                    self.peak_hist_ax_l.plot(
                        pen=et.utils.pg_pen_cycler(i), name="Distance {:d}".format(i)
                    )
                )
            if self.hist_plots["amplitude"][1]:
                self.hist_plots["amplitude"][0].append(
                    self.peak_hist_ax_r1.plot(
                        pen=et.utils.pg_pen_cycler(i), name="Amplitude {:d}".format(i)
                    )
                )

        self.smooth_max = et.utils.SmoothMax(
            self.sensor_config.update_rate,
            tau_decay=0.2,
            tau_grow=0.2,
        )

        self.plot_index = 0

    def update(self, data):
        nfft = data["fft_map"].shape[2]
        if self.plot_index == 0:
            nr_sensors = data["fft_map"].shape[0]
            spos = self.sensor_separation / 2
            pos0 = self.sensor_config.range_start * 100
            pos1 = self.sensor_config.range_end * 100
            num_points = data["env_ampl"].size
            self.env_xs = np.linspace(*self.sensor_config.range_interval * 100, num_points)
            self.peak_x = self.env_xs[data["peak_idx"]]

            tr = QtGui.QTransform()
            tr.translate(-self.max_velocity, pos0)
            tr.scale(
                2 * self.max_velocity / nfft,
                self.sensor_config.range_length * 100 / num_points,
            )
            self.obstacle_im.setTransform(tr)
            if self.advanced_plots["background_map"]:
                tr.translate(-self.max_velocity, pos0)
                tr.scale(
                    2 * self.max_velocity / nfft,
                    self.sensor_config.range_length * 100 / num_points,
                )
                self.obstacle_bg_im.setTransform(tr)

            if self.advanced_plots["threshold_map"]:
                tr.translate(-self.max_velocity, pos0)
                tr.scale(
                    2 * self.max_velocity / nfft,
                    self.sensor_config.range_length * 100 / num_points,
                )
                self.obstacle_thresh_im.setTransform(tr)

            show_fusion = self.advanced_plots["fusion_map"]
            show_shadows = self.advanced_plots["show_shadows"]
            if show_fusion:
                self.fusion_ax.setXRange(-pos1, pos1)
                self.fusion_ax.setYRange(pos0 - 10, pos1)
                self.left_sensor_text.setPos(-spos, pos0 - 10)
                self.right_sensor_text.setPos(spos, pos0 - 10)
                self.left_sensor.setValue(spos)
                self.right_sensor.setValue(-spos)
                self.left_sensor_rect.setRect(-spos - 1, pos0 - 1, 2, 2)
                self.right_sensor_rect.setRect(spos - 1, pos0 - 1, 2, 2)

                id1 = self.sensor_config.sensor[0]
                self.right_sensor_text.setText("Sensor {}".format(id1))
                if show_shadows:
                    self.fusion_legend.addItem(self.right_sensor_shadows, "Sensor {}".format(id1))
                if len(self.sensor_config.sensor) == 2:
                    id2 = self.sensor_config.sensor[1]
                    self.left_sensor_text.setText("Sensor {}".format(id2))
                    if show_shadows:
                        self.fusion_legend.addItem(
                            self.left_sensor_shadows, "Sensor {}".format(id2)
                        )

                if nr_sensors == 1:
                    self.left_sensor_text.hide()
                    self.left_sensor_rect.hide()
                else:
                    self.left_sensor_text.show()
                    self.left_sensor_rect.show()
        else:
            self.peak_x = self.peak_x * 0.7 + 0.3 * self.env_xs[data["peak_idx"]]

        peak_dist_text = "Peak: {:.1f} cm".format(self.peak_x)
        peak_fft_text = "No peaks found"

        if data["fft_peaks"] is not None:
            dist = self.env_xs[data["fft_peaks"][:, 0].astype(int)]
            vel = (data["fft_peaks"][:, 1] / data["fft_map"].shape[2] * 2 - 1) * self.max_velocity
            peak_fft_text = "Dist: {:.1f}cm, Speed/Angle: {:.1f}cm/s / {:.0f}".format(
                dist[0], data["velocity"], data["angle"]
            )

            half_pixel = self.max_velocity / np.floor(data["fft_map"].shape[2] / 2) / 2
            self.obstacle_peak.setData(vel + half_pixel, dist)
        else:
            self.obstacle_peak.setData([], [])

        if data["fft_bg_iterations_left"]:
            bg_text = "Stay clear of sensors, estimating background! {} iterations left"
            bg_text = bg_text.format(data["fft_bg_iterations_left"])
            peak_fft_text = ""
        else:
            bg_text = ""

        for i in range(self.nr_locals):
            if self.hist_plots["distance"][1]:
                self.hist_plots["distance"][0][i].setData(
                    np.arange(len(data["peak_hist"][i, 0, :])), data["peak_hist"][i, 0, :]
                )
            if self.hist_plots["velocity"][1]:
                self.hist_plots["velocity"][0][i].setData(
                    np.arange(len(data["peak_hist"][i, 1, :])), data["peak_hist"][i, 1, :]
                )
            if self.hist_plots["angle"][1]:
                self.hist_plots["angle"][0][i].setData(
                    np.arange(len(data["peak_hist"][i, 2, :])), data["peak_hist"][i, 2, :]
                )
            if self.hist_plots["amplitude"][1]:
                self.hist_plots["amplitude"][0][i].setData(
                    np.arange(len(data["peak_hist"][i, 3, :])), data["peak_hist"][i, 3, :]
                )

        map_max = np.max(np.max(data["fft_map"][0]))

        self.peak_dist_text.setText(peak_dist_text)
        self.peak_fft_text.setText(peak_fft_text)
        self.bg_estimation_text.setText(bg_text)

        self.env_ampl.setData(self.env_xs, data["env_ampl"])
        self.env_peak_vline.setValue(self.peak_x)

        fft_max = np.max(data["fft_max_env"])
        env_max = np.max(data["env_ampl"])
        env_max = max(env_max, fft_max)

        self.fft_max.setData(self.env_xs, data["fft_max_env"])

        if data["fft_bg"] is not None:
            self.fft_bg_data = data["fft_bg"]

        if self.advanced_plots["show_line_outs"]:
            max_index = 8
            max_bg = None
            if data["fft_peaks"] is not None:
                max_index = int(data["fft_peaks"][0, 1])
            else:
                try:
                    max_index = np.asarray(
                        unravel_index(np.argmax(data["fft_map"][0]), data["fft_map"][0].shape)
                    )[1]
                except Exception:
                    pass
            if self.fft_bg_data is not None:
                max_bg = self.fft_bg_data[:, max_index]
                self.fft_bg.setData(self.env_xs, max_bg)
                env_max = max(np.max(max_bg), env_max)
            if data["threshold_map"] is not None:
                self.threshold_data = data["threshold_map"]
            if self.threshold_data is not None:
                thresh_max = self.threshold_data[:, max_index]
                if max_bg is not None:
                    thresh_max = thresh_max + max_bg
                env_max = max(np.max(thresh_max), env_max)
                self.fft_thresh.setData(self.env_xs, thresh_max)

        self.env_ax.setYRange(0, self.smooth_max.update(env_max))

        fft_data = data["fft_map"][0].T
        if self.fft_bg_data is not None:
            max_wo_bg = map_max
            fft_data = fft_data - self.fft_bg_data.T
            fft_data[fft_data < 0] = 0
            map_max = np.max(fft_data)
            self.peak_val_text.setText("FFT max: {:.3f} ({:.3f})".format(map_max, max_wo_bg))
        else:
            self.peak_val_text.setText("FFT max: {:.3f}".format(map_max))

        g = 1 / 2.2
        fft_data = 254 / (map_max + 1.0e-9) ** g * fft_data ** g

        fft_data[fft_data > 254] = 254

        map_min = -1
        map_max = 257

        self.obstacle_im.updateImage(fft_data, levels=(map_min, map_max))

        if data["threshold_map"] is not None and self.advanced_plots["threshold_map"]:
            thresh_max = np.max(data["threshold_map"])
            levels = (0, thresh_max * 1.05)
            self.obstacle_thresh_im.updateImage(data["threshold_map"].T, levels=levels)

        if data["fft_bg"] is not None and self.advanced_plots["background_map"]:
            map_max = np.max(np.max(data["fft_bg"]))
            fft_data = data["fft_bg"].T
            fft_data = 254 / (map_max + 1e-6) ** g * fft_data ** g

            fft_data[fft_data > 254] = 254

            map_min = -1
            map_max = 257

            self.obstacle_bg_im.updateImage(fft_data, levels=(map_min, map_max))

        if self.advanced_plots["fusion_map"]:
            self.fusion_scatter.setData(
                data["fused_obstacles"][0][0, :],
                data["fused_obstacles"][1][0, :],
            )
            for i in range(self.fusion_max_obstacles):
                self.fusion_hist[i].setData(
                    data["fused_obstacles"][0][:, i],
                    data["fused_obstacles"][1][:, i],
                )
            if self.advanced_plots["show_shadows"]:
                self.left_sensor_shadows.setData(
                    data["left_shadows"][0][0, :],
                    data["left_shadows"][1][0, :],
                )
                self.right_sensor_shadows.setData(
                    data["right_shadows"][0][0, :],
                    data["right_shadows"][1][0, :],
                )
        self.plot_index += 1
