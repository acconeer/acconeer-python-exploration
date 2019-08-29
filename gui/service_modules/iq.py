import numpy as np
from PyQt5 import QtCore
import pyqtgraph as pg

from acconeer_utils.clients import configs
from acconeer_utils import example_utils

import logging

log = logging.getLogger("acconeer_utils.examples.gui_iq")


def get_processing_config():
    return {
        "image_buffer": {
            "name": "Image history",
            "value": 100,
            "limits": [10, 16384],
            "type": int,
            "text": None,
        },
        "averaging": {
            "name": "Averaging",
            "value": 0,
            "limits": [0, 0.9999],
            "type": float,
            "text": None,
        },
    }


def get_sensor_config():
    return configs.IQServiceConfig()


class IQProcessor:
    def __init__(self, sensor_config, processing_config):
        self.data_processing = processing_config["processing_handle"]
        self.sensor_config = sensor_config
        self.mode = self.sensor_config.mode
        self.start_x = self.sensor_config.range_interval[0]
        self.stop_x = self.sensor_config.range_interval[1]
        self.sweep = 0
        self.time_filter = processing_config["averaging"]["value"]

        if "create_clutter" in processing_config:
            self.create_cl = processing_config["create_clutter"]
            self.use_cl = processing_config["use_clutter"]
            self.cl_file = processing_config["clutter_file"]
            self.sweeps = processing_config["sweeps_requested"]
        else:
            self.create_cl = None
            self.use_cl = None
            self.cl_file = None
            self.sweeps = -1

        self.rate = 1/self.sensor_config.sweep_rate

        self.image_buffer = processing_config["image_buffer"]["value"]

        if self.sweeps < 0:
            self.sweeps = self.image_buffer

        if self.create_cl:
            self.sweeps = max(self.sweeps, 100)

    def update_processing_config(self, processing_config):
        self.use_cl = processing_config["use_clutter"]

    def process(self, sweep):
        snr = {}
        peak_data = {}

        if len(sweep.shape) == 1:
            sweep = np.expand_dims(sweep, 0)

        if self.sweep == 0:
            self.num_sensors, self.data_len = sweep.shape
            self.env_x_mm = np.linspace(self.start_x, self.stop_x, self.data_len) * 1000

            self.cl_empty = np.zeros(self.data_len)
            self.last_iq = np.zeros((self.num_sensors, self.data_len))

            if self.num_sensors == 1:
                self.cl, self.cl_iq, self.n_std_avg = \
                    self.data_processing.load_clutter_data(self.data_len, self.cl_file)
            else:
                self.cl = self.cl_iq = self.n_std_avg = self.cl_empty
                self.create_cl = False
                if self.use_cl:
                    print("Background not supported for multiple sensors!")
                    self.use_cl = False

            self.hist_env = np.zeros(
                (self.num_sensors, len(self.env_x_mm), self.image_buffer)
                )
            self.peak_history = np.zeros(
                (self.num_sensors, self.image_buffer),
                dtype="float"
                )

        iq = sweep.copy()

        for s in range(self.num_sensors):
            if self.use_cl:
                try:
                    iq[s, :] = iq[s, :] - self.cl_iq
                except Exception as e:
                    log.error("Background has wrong format!\n{}".format(e))
                    self.use_cl = False
                    self.cl = self.cl_iq = np.zeros(len(self.cl))

            time_filter = self.time_filter
            if time_filter >= 0:
                if self.sweep < np.ceil(1.0 / (1.0 - self.time_filter) - 1):
                    time_filter = min(1.0 - 1.0 / (self.sweep + 1), self.time_filter)
                if self.sweep:
                    iq[s, :] = (1 - time_filter) * iq[s, :] + time_filter * self.last_iq[s, :]
                self.last_iq[s, :] = iq[s, :].copy()

        env = np.abs(iq)

        if self.create_cl:
            if self.sweep == 0:
                self.cl = np.zeros((self.sweeps, self.data_len))
                self.cl_iq = np.zeros((self.sweeps, self.data_len), dtype="complex")
            self.cl[self.sweep, :] = env[0, :]
            self.cl_iq[self.sweep, :] = iq[0, :]

        peak_data = {
            'peak_idx': np.zeros(self.num_sensors),
            'peak_mm': np.zeros(self.num_sensors),
            'peak_amp': np.zeros(self.num_sensors),
            'snr': np.zeros(self.num_sensors),
            }
        env_max = np.zeros(self.num_sensors)
        phase = np.zeros((self.num_sensors, self.data_len))

        hist_plots = []
        for s in range(self.num_sensors):
            peak_idx = np.argmax(env[s, :])
            peak_mm = self.env_x_mm[peak_idx]
            if peak_mm <= self.start_x * 1000:
                peak_mm = self.stop_x * 1000
            peak_data['peak_mm'][s] = peak_mm
            peak_data['peak_idx'][s] = peak_idx
            env_max[s] = np.max(env[s, :])
            peak_data['peak_amp'][s] = env_max[s]

            snr = None
            signal = env[s, peak_idx]
            if self.use_cl and self.n_std_avg[peak_idx] > 0:
                noise = self.n_std_avg[peak_idx]
                snr = 20*np.log10(signal / noise)
            else:
                # Simple noise estimate: noise ~ mean(envelope)
                noise = np.mean(env[s, :])
                snr = 20*np.log10(signal / noise)
            peak_data["snr"][s] = snr

            p = np.angle(iq[s, :])
            p /= np.max(np.abs(p))

            phase[s, :] = p

            hist_plots.append(np.flip(self.peak_history[s, :], axis=0))
            self.peak_history[s, :] = np.roll(self.peak_history[s, :], 1)
            self.peak_history[s, 0] = peak_mm

            self.hist_env[s, :, :] = np.roll(self.hist_env[s, :, :], 1, axis=1)
            self.hist_env[s, :, 0] = env[s, :]

        cl = self.cl
        cl_iq = self.cl_iq
        if self.create_cl:
            cl = self.cl[self.sweep, :]
            cl_iq = self.cl_iq[self.sweep, :]
        elif not self.use_cl:
            cl = self.cl_empty
            cl_iq = self.cl_empty

        plot_data = {
            "iq_data": iq,
            "env_ampl": env,
            "phase": phase,
            "env_clutter": cl,
            "iq_clutter": cl_iq,
            "clutter_raw": self.cl_iq,
            "env_max": env_max,
            "n_std_avg": self.n_std_avg,
            "hist_plots": hist_plots,
            "hist_env": self.hist_env,
            "sensor_config": self.sensor_config,
            "peaks": peak_data,
            "x_mm": self.env_x_mm,
            "cl_file": self.cl_file,
            "sweep": self.sweep,
            "num_sensors": self.num_sensors,
        }

        self.sweep += 1

        return plot_data


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config
        self.num_sensors = len(sensor_config.sensor)

    def setup(self, win):
        win.setWindowTitle("Acconeer IQ mode example")
        self.envelope_plot_window = win.addPlot(row=0, col=0, title="Envelope",
                                                colspan=self.num_sensors)
        self.envelope_plot_window.showGrid(x=True, y=True)
        self.envelope_plot_window.addLegend(offset=(-10, 10))
        self.envelope_plot_window.setYRange(0, 1)
        self.envelope_plot_window.setLabel("left", "Amplitude")
        self.envelope_plot_window.setLabel("bottom", "Distance (mm)")

        self.peak_text = pg.TextItem(text="", color=(1, 1, 1), anchor=(0, 1), fill="#f0f0f0")
        self.peak_text.setZValue(3)
        self.envelope_plot_window.addItem(self.peak_text)

        self.phase_plot_window = win.addPlot(row=1, col=0, title="Phase", colspan=self.num_sensors)
        self.phase_plot_window.showGrid(x=True, y=True)
        self.phase_plot_window.addLegend(offset=(-10, 10))
        self.phase_plot_window.setLabel("left", "Normalized phase")
        self.phase_plot_window.setLabel("bottom", "Distance (mm)")

        self.envelope_plots = []
        self.peak_vlines = []
        self.clutter_plots = []
        self.phase_plots = []
        self.hist_plot_images = []
        self.hist_plots = []
        self.hist_plot_peaks = []

        lut = example_utils.pg_mpl_cmap("viridis")
        hist_pen = example_utils.pg_pen_cycler(1)

        for s in range(self.num_sensors):
            legend_text = "Sensor {}".format(self.sensor_config.sensor[s])
            pen = example_utils.pg_pen_cycler(s+1)
            self.envelope_plots.append(
                self.envelope_plot_window.plot(range(10), np.zeros(10), pen=pen, name=legend_text)
                )
            self.peak_vlines.append(
                pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2, style=QtCore.Qt.DotLine))
                )
            self.envelope_plot_window.addItem(self.peak_vlines[s])

            self.phase_plots.append(
                self.phase_plot_window.plot(range(10), np.arange(10)*0, pen=pen, name=legend_text)
                    )

            hist_title = "Envelope history"
            if self.num_sensors == 1:
                pen = pg.mkPen(0.2, width=2, style=QtCore.Qt.DotLine)
                self.clutter_plots.append(
                    self.envelope_plot_window.plot(
                        range(10),
                        np.zeros(10),
                        pen=pen,
                        name="Background")
                    )
                self.clutter_plots[0].setZValue(2)
            else:
                hist_title = "History {}".format(legend_text)

            self.hist_plot_images.append(win.addPlot(row=2, col=s,
                                                     title=hist_title))
            self.hist_plot_images[s].setLabel("left", "Distance (mm)")
            self.hist_plot_images[s].setLabel("bottom", "Time (s)")
            self.hist_plots.append(pg.ImageItem())
            self.hist_plots[s].setAutoDownsample(True)
            self.hist_plots[s].setLookupTable(lut)
            self.hist_plot_images[s].addItem(self.hist_plots[s])

            self.hist_plot_peaks.append(
                self.hist_plot_images[s].plot(range(10), np.zeros(10), pen=hist_pen))

    def update(self, data):
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        xdim = data["hist_env"].shape[1]

        num_sensors = len(data["env_ampl"])
        if self.num_sensors < num_sensors:
            num_sensors = self.num_sensors

        if data["sweep"] <= 1:
            self.env_plot_max_y = np.zeros(self.num_sensors)
            self.envelope_plot_window.setXRange(xstart, xend)
            self.phase_plot_window.setXRange(xstart, xend)
            self.phase_plot_window.setYRange(-1.1, 1.1)

            self.smooth_envelope = example_utils.SmoothMax(
                int(self.sensor_config.sweep_rate),
                tau_decay=1,
                tau_grow=0.2
                )

            for s in range(num_sensors):
                self.peak_text.setPos(xstart, 0)

                yax = self.hist_plot_images[s].getAxis("left")
                y = np.round(np.arange(0, xdim+xdim/9, xdim/9))
                labels = np.round(np.arange(xstart, xend+(xend-xstart)/9,
                                  (xend-xstart)/9))
                ticks = [list(zip(y, labels))]
                yax.setTicks(ticks)
                self.hist_plot_images[s].setYRange(0, xdim)

                s_buff = data["hist_env"].shape[2]
                t_buff = s_buff / data["sensor_config"].sweep_rate
                tax = self.hist_plot_images[s].getAxis("bottom")
                t = np.round(np.arange(0, s_buff + 1, s_buff / min(10 / self.num_sensors, s_buff)))
                labels = np.round(t / s_buff * t_buff, decimals=3)
                ticks = [list(zip(t, labels))]
                tax.setTicks(ticks)

        peaks = data["peaks"]
        peak_txt = "Peak: N/A"
        for s in range(num_sensors):
            sensor = self.sensor_config.sensor[s]
            if peaks:
                self.peak_vlines[s].setValue(peaks["peak_mm"][s])
                if s == 0:
                    peak_txt = ""
                if np.isfinite(peaks["snr"][s]):
                    peak_txt += "Peak S{}: {:.1f}mm, SNR: {:.1f}dB".format(
                        sensor, peaks["peak_mm"][s], peaks["snr"][s])
                else:
                    peak_txt += "Peak S{}: %.1fmm".format(sensor, peaks["peak_mm"][s])
                if s < num_sensors - 1:
                    peak_txt += "\n"

            max_val = max(np.max(data["env_clutter"] + data["env_ampl"][s]),
                          np.max(data["env_clutter"]))
            peak_line = np.flip((data["hist_plots"][s] - xstart) / (xend - xstart) * xdim, axis=0)

            self.envelope_plots[s].setData(data["x_mm"], data["env_ampl"][s] + data["env_clutter"])
            self.phase_plots[s].setData(data["x_mm"], data["phase"][s])

            self.envelope_plot_window.setYRange(0, self.smooth_envelope.update(max_val))

            if num_sensors == 1 and len(self.clutter_plots):
                self.clutter_plots[0].setData(data["x_mm"], data["env_clutter"])

            ymax_level = min(1.5 * np.max(np.max(data["hist_env"][s, :, :])),
                             self.env_plot_max_y[s])

            self.hist_plots[s].updateImage(data["hist_env"][s, :, :].T, levels=(0, ymax_level))
            self.hist_plot_peaks[s].setData(peak_line)
            self.hist_plot_peaks[s].setZValue(2)

            if max_val > self.env_plot_max_y[s]:
                self.env_plot_max_y[s] = 1.2 * max_val
        self.peak_text.setText(peak_txt, color=(1, 1, 1))
