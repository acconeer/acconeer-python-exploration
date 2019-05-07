import numpy as np
from numpy import pi, unravel_index
from PyQt5 import QtCore
import pyqtgraph as pg
from scipy.fftpack import fft, fftshift

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils
from acconeer_utils.pg_process import PGProcess, PGProccessDiedException

import logging
log = logging.getLogger("acconeer_utils.examples.obstacle_detection")

MAX_SPEED = 8.00   # Max speed to be resolved with FFT in cm/s
WAVELENGTH = 0.49  # Wavelength of radar in cm


def main():
    args = example_utils.ExampleArgumentParser(num_sens=1).parse_args()
    example_utils.config_logging(args)

    if args.socket_addr:
        client = JSONClient(args.socket_addr)
    elif args.spi:
        client = RegSPIClient()
    else:
        port = args.serial_port or example_utils.autodetect_serial_port()
        client = RegClient(port)

    sensor_config = get_sensor_config()
    processing_config = get_processing_config()
    sensor_config.sensor = args.sensors

    client.setup_session(sensor_config)

    pg_updater = PGUpdater(sensor_config, processing_config)
    pg_process = PGProcess(pg_updater)
    pg_process.start()

    client.start_streaming()

    interrupt_handler = example_utils.ExampleInterruptHandler()
    print("Press Ctrl-C to end session")

    processor = ObstacleDetectionProcessor(sensor_config, processing_config)

    while not interrupt_handler.got_signal:
        info, sweep = client.get_next()
        plot_data = processor.process(sweep)

        if plot_data is not None:
            try:
                pg_process.put_data(plot_data)
            except PGProccessDiedException:
                break

    print("Disconnecting...")
    pg_process.close()
    client.disconnect()


def get_sensor_config():
    config = configs.IQServiceConfig()
    config.range_interval = [0.1, 0.5]
    config.sweep_rate = int(np.ceil(MAX_SPEED * 4 / WAVELENGTH))
    config.gain = 0.7
    return config


def get_processing_config():
    return {
        "fft_length": {
            "name": "FFT length",
            "value": 16,
            "limits": [2, 512],
            "type": int,
        },
        "threshold": {  # Ignore data below threshold in FFT window for moving objects
            "name": "Moving Threshold",
            "value": 0.1,
            "limits": [0.0, 100],
            "type": float,
        },
        "v_max": {
            "name": None,
            "value": None,
            "limits": None,
            "type": None,
            "text": "Max velocity = 4.9mm * freq / 4",
        },
        "downsampling": {
            "name": "Downsample scale",
            "value": 8,
            "limits": [0, 124],
            "type": int,
            "advanced": True,
        },
        "calib": {
            "name": "Background iterations",
            "value": 0,
            "limits": [0, 1000],
            "type": int,
            "advanced": True,
        },
        "bg_offset": {
            "name": "Background Scale",
            "value": 1.6,
            "limits": [0, 1000],
            "type": float,
            "advanced": True,
        },
        "static_threshold": {  # Ignore data below threshold in FFT window for static objects
            "name": "Stationary Threshold",
            "value": 0.1,
            "limits": [0.0, 100],
            "type": float,
            "advanced": True,
        },
        "close_threshold_addition": {  # Ignore data below threshold for very close range
            "name": "Close Threshold Addition",
            "value": 0.1,
            "limits": [0.0, 100],
            "type": float,
            "advanced": True,
        },
        "static_distance": {
            "name": "Distance limit far",
            "value": 25,
            "limits": [0.0, 1000],
            "type": float,
            "advanced": True,
        },
        "static_grad": {
            "name": "Static distance gradient",
            "value": 6,
            "limits": [0.0, 100],
            "type": float,
            "advanced": True,
        },
        "close_dist": {
            "name": "Distance limit near",
            "value": 16,
            "limits": [0.0, 100],
            "type": float,
            "advanced": True,
        },
        "static_freq": {
            "name": "Static frequency gradient",
            "value": 2,
            "limits": [0.0, 100],
            "type": float,
            "advanced": True,
        },
        "nr_peaks": {
            "name": "Number of peaks",
            "value": 1,
            "limits": [0, 100],
            "type": int,
            "advanced": True,
        },
        "edge_to_peak": {
            "name": "Edge to peak ratio",
            "value": 1,
            "limits": [0, 1],
            "type": float,
            "advanced": True,
        },
        "peak_hist": {
            "name": "Peak history",
            "value": 500,
            "limits": [50, 2000],
            "type": int,
            "advanced": True,
        },
        "robot_velocity": {
            "name": "Robot Velocity [cm/s]",
            "value": 6,
            "limits": [-1000, 1000],
            "type": float,
            "advanced": True,
        },
        "background_map": {
            "name": "Show background (from background iterations)",
            "value": False,
            "advanced": True,
        },
        "threshold_map": {
            "name": "Show threshold map",
            "value": False,
            "advanced": True,
        },
        "distance_history": {
            "name": "Show distance history",
            "value": False,
            "advanced": True,
        },
        "velocity_history": {
            "name": "Show velocity history",
            "value": False,
            "advanced": True,
        },
        "angle_history": {
            "name": "Show angle history",
            "value": True,
            "advanced": True,
        },
        # Allows saving and loading from GUI
        "send_process_data": {
            "value": None,
            "text": "FFT background",
        },
    }


class ObstacleDetectionProcessor:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config
        self.fft_len = processing_config["fft_length"]["value"]
        self.threshold = processing_config["threshold"]["value"]
        self.static_threshold = processing_config["static_threshold"]["value"]
        self.static_distance = processing_config["static_distance"]["value"]
        self.close_threshold_addition = processing_config["close_threshold_addition"]["value"]
        self.sweep_index = 0
        self.use_bg = max(processing_config["calib"]["value"], 0)
        self.bg_off = processing_config["bg_offset"]["value"]
        self.saved_bg = processing_config["send_process_data"]["value"]
        self.bg_avg = 0
        self.peak_hist_len = processing_config["peak_hist"]["value"]
        self.nr_locals = processing_config["nr_peaks"]["value"]
        self.static_freq_limit = processing_config["static_freq"]["value"]
        self.static_dist_gradient = processing_config["static_grad"]["value"]
        self.close_dist_limit = processing_config["close_dist"]["value"]
        self.robot_velocity = processing_config["robot_velocity"]["value"]
        self.edge_ratio = processing_config["edge_to_peak"]["value"]
        self.downsampling = processing_config["downsampling"]["value"]

    def process(self, sweep):
        if self.downsampling:
            sweep = sweep[::self.downsampling]

        if self.sweep_index == 0 and self.bg_avg == 0:
            len_range = len(sweep)
            self.sweep_map = np.zeros((len_range, self.fft_len), dtype="complex")
            self.fft_bg = np.zeros((len_range, self.fft_len))
            self.hamming_map = np.zeros((len_range, self.fft_len))
            for i in range(len_range):
                self.hamming_map[i, :] = np.hamming(self.fft_len)
            self.env_xs = np.linspace(*self.sensor_config.range_interval * 100, len(sweep))
            self.peak_hist = np.zeros((self.nr_locals, 3, self.peak_hist_len)) * float('nan')
            self.mask = np.zeros((len_range, self.fft_len))
            self.threshold_map = np.zeros((len_range, self.fft_len))

            if self.saved_bg is not None:
                if hasattr(self.saved_bg, "shape") and self.saved_bg.shape == self.fft_bg.shape:
                    self.fft_bg = self.saved_bg
                    self.use_bg = False
                    log.info("Using saved FFT background data!")
                else:
                    log.warn("Saved background has wrong shape/type!")
                    log.warn("Required shape {}".format(self.fft_bg.shape))
                    if hasattr(self.saved_bg, "shape"):
                        log.warn("Supplied shape {}".format(self.saved_bg.shape))

            for dist in range(len_range):
                for freq in range(self.fft_len):
                    self.threshold_map[dist, freq] = self.variable_thresholding(
                        freq, dist, self.threshold, self.static_threshold)

        self.push(sweep, self.sweep_map)

        signalFFT = fftshift(fft(self.sweep_map*self.hamming_map, axis=1), axes=1)
        signalPSD = np.square(np.abs(signalFFT))
        if self.use_bg and self.sweep_index == self.fft_len - 1:
            self.fft_bg = np.maximum(self.bg_off*signalPSD, self.fft_bg)

            self.bg_avg += 1
            if self.bg_avg < self.use_bg:
                self.sweep_index = 0

        signalPSD -= self.fft_bg
        signalPSD[signalPSD < 0] = 0
        env = np.abs(sweep)

        fft_peaks, peaks_found = self.find_peaks(signalPSD)
        fft_max_env = env
        angle = None
        velocity = None
        peak_idx = np.argmax(env)
        dist_normal = None

        if self.sweep_index < self.fft_len:
            fft_peaks = None

        if fft_peaks is not None:
            fft_max_env = signalPSD[:, int(fft_peaks[0, 1])]
            zero = np.floor(self.fft_len / 2)

            for i in range(self.nr_locals):
                bin_index = (fft_peaks[i, 2] - zero)
                velocity = (bin_index / zero) * WAVELENGTH * self.sensor_config.sweep_rate / 4
                angle = np.arccos(self.clamp(velocity / self.robot_velocity, -1.0, 1.0)) / pi * 180
                peak_idx = int(fft_peaks[i, 0])
                distance = self.env_xs[int(fft_peaks[i, 0])]
                dist_normal = np.cos(angle / 180 * np.pi) * distance

                peak_val = fft_peaks[i, 4]
                if not peak_val:
                    distance = float(np.nan)
                    velocity = float(np.nan)
                    angle = float(np.nan)
                self.push_vec(distance, self.peak_hist[i, 0, :])
                self.push_vec(velocity, self.peak_hist[i, 1, :])
                self.push_vec(angle, self.peak_hist[i, 2, :])
            fft_peaks = fft_peaks[:peaks_found, :]
        else:
            for i in range(self.nr_locals):
                self.push_vec(float(np.nan), self.peak_hist[i, 0, :])
                self.push_vec(float(np.nan), self.peak_hist[i, 1, :])
                self.push_vec(float(np.nan), self.peak_hist[i, 2, :])

        fft_bg = None
        if self.sweep_index in range(self.fft_len + 1, self.fft_len + 5):
            fft_bg = self.fft_bg

        threshold_map = None
        if self.sweep_index == 1:
            threshold_map = self.threshold_map

        out_data = {
            "env_ampl": env,
            "fft_max_env": fft_max_env,
            "fft_map": signalPSD,
            "peak_idx": peak_idx,
            "angle": angle,
            "velocity": velocity,
            "fft_peaks": fft_peaks,
            "dist_normal": dist_normal,
            "peak_hist": self.peak_hist,
            "fft_bg": fft_bg,
            "threshold_map": threshold_map,
            "send_process_data": fft_bg,
        }

        self.sweep_index += 1
        return out_data

    def remap(self, val, x1, x2, y1, y2):
        m = (y2 - y1) / (x2 - x1)
        b = y1 - m * x1
        return val * m + b

    def clamp(self, val, a, b):
        val = max(val, a)
        val = min(val, b)
        return val

    def push(self, sweep, arr):
        res = np.empty_like(arr)
        res[:, 0] = sweep
        res[:, 1:] = arr[:, :-1]
        arr[...] = res

    def push_vec(self, val, vec):
        res = np.empty_like(vec)
        res[0] = val
        res[1:] = vec[:-1]
        vec[...] = res

    def find_peaks(self, arr, dead_zone=2):
        if not self.nr_locals:
            return None, 0

        peaks_found = 0
        peak = np.asarray(unravel_index(np.argmax(arr), arr.shape))
        peak_avg = peak[1]

        peak_val = arr[peak[0], peak[1]]
        thresh = self.variable_thresholding(peak[1], peak[0], self.threshold,
                                            self.static_threshold)

        if peak_val < thresh:
            peak = None
            peak_avg = None

        if peak is not None:
            peak_avg = self.calc_peak_avg(peak, arr)
            local_peaks = np.zeros((self.nr_locals, 5), dtype=float)
            local_peaks[0, 0:2] = peak
            local_peaks[0, 2] = peak_avg
            local_peaks[0, 3] = np.round(peak_val, decimals=4)
            local_peaks[0, 4] = thresh
            peaks_found += 1
            self.mask = arr.copy()

            for i in range(self.nr_locals - 1):
                self.peak_masking(local_peaks[i, :])
                p = np.asarray(unravel_index(np.argmax(self.mask), arr.shape))
                thresh = self.variable_thresholding(p[1], p[0],
                                                    self.threshold, self.static_threshold)
                peak_val = arr[p[0], p[1]]
                if peak_val > thresh:
                    dist_edge = self.edge(arr[:, p[1]], p[0], self.edge_ratio)
                    local_peaks[i + 1, 0] = dist_edge
                    local_peaks[i + 1, 1] = p[1]
                    local_peaks[i + 1, 2] = self.calc_peak_avg(p, arr)
                    local_peaks[i + 1, 3] = np.round(peak_val, decimals=4)
                    local_peaks[i + 1, 4] = thresh
                    peaks_found += 1
                else:
                    break
            return local_peaks, peaks_found
        else:
            return None, 0

    def calc_peak_avg(self, peak, arr):
        amp_sum = 0
        s = 0
        for i in range(3):
            idx_real = peak[1] - 1 + i
            idx = idx_real
            if idx == self.fft_len:
                idx = 0
            elif idx == -1:
                idx = self.fft_len - 1
            s += arr[peak[0], idx] * idx_real
            amp_sum += arr[peak[0], idx]
        peak_avg = s / amp_sum

        peak_avg = max(0, peak_avg)

        return peak_avg % self.fft_len

    def peak_masking(self, peak, angle_depth=2, depth=180, amplitude_margin=1.2):
        dist_depth = depth / self.downsampling

        distance_index = peak[0]
        angle_index = peak[1]
        peak_val = peak[3]

        dist_len, angle_len = self.mask.shape

        distance_scaling_per_index = 1 / dist_depth
        angle_scaling_per_index = 1 / (1 + angle_depth)

        distance_start_index = - dist_depth

        if distance_start_index + distance_index < 0:
            distance_start_index = - distance_index

        distance_end_index = dist_depth
        if distance_end_index + distance_index >= dist_len:
            distance_end_index = dist_len - distance_index - 1

        for i in range(-angle_depth, angle_depth + 1):
            wrapped_row = (angle_len + i + angle_index) % angle_len
            for j in range(int(distance_start_index), int(distance_end_index) + 1):
                dist_from_peak = abs(i) * angle_scaling_per_index \
                    + abs(j) * distance_scaling_per_index
                mask_val = (1 - dist_from_peak**2) * peak_val * amplitude_margin
                if self.mask[int(j + distance_index), int(wrapped_row)] < mask_val:
                    self.mask[int(j + distance_index), int(wrapped_row)] = 0

    def edge(self, arr, peak_idx, ratio=0.5):
        if ratio == 1.0:
            return peak_idx

        s0 = arr[peak_idx]
        for i in range(peak_idx):
            if peak_idx-i < 0:
                peak_idx = 0
                break
            if arr[peak_idx-i] < s0*ratio:
                peak_idx -= i
                break

        return peak_idx

    def variable_thresholding(self, freq_index, dist_index, min_thresh, max_thresh):
        dist = self.env_xs[dist_index]
        distance_gradient = self.static_dist_gradient
        thresh = self.remap(dist, self.static_distance - distance_gradient, self.static_distance,
                            max_thresh, min_thresh)
        thresh = self.clamp(thresh, min_thresh, max_thresh)

        null_frequency = self.fft_len / 2
        frequency_gradient = self.static_freq_limit

        if freq_index <= null_frequency:
            freq = self.clamp(freq_index, null_frequency - frequency_gradient, null_frequency)
            thresh = self.remap(freq,
                                null_frequency - frequency_gradient, null_frequency,
                                min_thresh, thresh)
        else:
            freq = self.clamp(freq_index, null_frequency, null_frequency + frequency_gradient)
            thresh = self.remap(freq,
                                null_frequency, null_frequency + frequency_gradient,
                                thresh, min_thresh)

        thresh_add = self.close_threshold_addition * (self.close_dist_limit-dist) / \
            (self.close_dist_limit - self.sensor_config.range_interval[0] * 100)
        thresh += self.clamp(thresh_add, 0, self.close_threshold_addition)

        return thresh


class PGUpdater:
    def __init__(self, sensor_config, processing_config):
        self.sensor_config = sensor_config
        self.plot_index = 0
        self.map_max = 0
        self.width = 3
        self.max_velocity = WAVELENGTH / 4 * self.sensor_config.sweep_rate  # cm/s
        self.peak_hist_len = processing_config["peak_hist"]["value"]
        self.dist_index = processing_config["downsampling"]["value"]
        self.nr_locals = processing_config["nr_peaks"]["value"]
        self.downsampling = processing_config["downsampling"]["value"]

        self.hist_plots = {
            "velocity": [[], processing_config["velocity_history"]["value"]],
            "angle":    [[], processing_config["angle_history"]["value"]],
            "distance": [[], processing_config["distance_history"]["value"]],
        }
        self.num_hist_plots = 0
        for hist in self.hist_plots:
            if hist[1]:
                self.num_hist_plots += 1
        self.advanced_plots = {
            "background_map": processing_config["background_map"]["value"],
            "threshold_map":  processing_config["threshold_map"]["value"],
        }

    def setup(self, win):
        win.setWindowTitle("Acconeer obstacle detection example")

        row_idx = 0
        self.env_ax = win.addPlot(row=row_idx, col=0, colspan=3, title="Envelope and max FFT")
        self.env_ax.setLabel("bottom", "Depth (cm)")
        self.env_ax.setXRange(*(self.sensor_config.range_interval * 100))
        self.env_ax.showGrid(True, True)
        self.env_ax.addLegend()
        self.env_ax.setYRange(0, 0.1)

        self.env_ampl = self.env_ax.plot(pen=example_utils.pg_pen_cycler(0), name="Envelope")
        self.fft_max = self.env_ax.plot(pen=example_utils.pg_pen_cycler(1, "--"), name="FFT max")

        self.peak_dist_text = pg.TextItem(color="k", anchor=(0, 1))
        self.env_ax.addItem(self.peak_dist_text)
        self.peak_dist_text.setPos(self.sensor_config.range_start*100, 0)
        self.peak_dist_text.setZValue(3)

        self.env_peak_vline = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2,
                                              style=QtCore.Qt.DotLine))
        self.env_ax.addItem(self.env_peak_vline)
        row_idx += 1

        self.obstacle_ax = win.addPlot(row=row_idx, col=0, colspan=self.num_hist_plots,
                                       title="Obstacle map")
        self.obstacle_im = pg.ImageItem()
        self.obstacle_ax.setLabel("bottom", "Velocity (cm/s)")
        self.obstacle_ax.setLabel("left", "Distance (cm)")
        self.obstacle_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
        self.obstacle_ax.addItem(self.obstacle_im)

        self.obstacle_ax.setXRange(-self.max_velocity, self.max_velocity)
        self.obstacle_ax.setYRange(*self.sensor_config.range_interval * 100)

        self.obstacle_ax.setXRange(-self.max_velocity, self.max_velocity)
        self.obstacle_ax.setYRange(*self.sensor_config.range_interval * 100)

        self.obstacle_peak = pg.ScatterPlotItem(brush=pg.mkBrush("k"), size=15)
        self.obstacle_ax.addItem(self.obstacle_peak)

        self.peak_fft_text = pg.TextItem(color="w", anchor=(0, 1))
        self.obstacle_ax.addItem(self.peak_fft_text)
        self.peak_fft_text.setPos(-self.max_velocity, self.sensor_config.range_start*100)

        self.peak_val_text = pg.TextItem(color="w", anchor=(0, 0))
        self.obstacle_ax.addItem(self.peak_val_text)
        self.peak_val_text.setPos(-self.max_velocity, self.sensor_config.range_end*100)

        row_idx += 1
        if self.advanced_plots["background_map"]:
            self.obstacle_bg_ax = win.addPlot(row=row_idx, col=0, colspan=self.num_hist_plots,
                                              title="Obstacle background")
            self.obstacle_bg_im = pg.ImageItem()
            self.obstacle_bg_ax.setLabel("bottom", "Velocity (cm/s)")
            self.obstacle_bg_ax.setLabel("left", "Distance (cm)")
            self.obstacle_bg_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
            self.obstacle_bg_ax.addItem(self.obstacle_bg_im)
            row_idx += 1

        if self.advanced_plots["threshold_map"]:
            self.obstacle_thresh_ax = win.addPlot(row=row_idx, col=0, colspan=self.num_hist_plots,
                                                  title="Obstacle threshold")
            self.obstacle_thresh_im = pg.ImageItem()
            self.obstacle_thresh_ax.setLabel("bottom", "Velocity (cm/s)")
            self.obstacle_thresh_ax.setLabel("left", "Distance (cm)")
            self.obstacle_thresh_im.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
            self.obstacle_thresh_ax.addItem(self.obstacle_thresh_im)
            row_idx += 1

        hist_col = 0
        row_idx += self.num_hist_plots
        if self.hist_plots["distance"][1]:
            self.peak_hist_ax_l = win.addPlot(row=row_idx, col=hist_col, title="Distance history")
            self.peak_hist_ax_l.setLabel("bottom", "Sweep")
            self.peak_hist_ax_l.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_l.showGrid(True, True)
            self.peak_hist_ax_l.addLegend(offset=(-10, 10))
            self.peak_hist_ax_l.setYRange(self.sensor_config.range_start*100,
                                          self.sensor_config.range_end*100)
            hist_col += 1

        if self.hist_plots["velocity"][1]:
            self.peak_hist_ax_c = win.addPlot(row=row_idx, col=hist_col, title="Velocity history")
            self.peak_hist_ax_c.setLabel("bottom", "Sweep")
            self.peak_hist_ax_c.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_c.showGrid(True, True)
            self.peak_hist_ax_c.addLegend(offset=(-10, 10))
            hist_col += 1

        if self.hist_plots["angle"][1]:
            self.peak_hist_ax_r = win.addPlot(row=row_idx, col=hist_col, title="Angle history")
            self.peak_hist_ax_r.setLabel("bottom", "Sweep")
            self.peak_hist_ax_r.setXRange(0, self.peak_hist_len)
            self.peak_hist_ax_r.showGrid(True, True)
            self.peak_hist_ax_r.addLegend(offset=(-10, 10))
            self.peak_hist_ax_r.setYRange(0, 180)
            hist_col += 1

        for i in range(self.nr_locals):
            if self.hist_plots["velocity"][1]:
                self.hist_plots["velocity"][0].append(
                    self.peak_hist_ax_c.plot(pen=example_utils.pg_pen_cycler(i),
                                             name="Veloctiy {:d}".format(i)))
            if self.hist_plots["angle"][1]:
                self.hist_plots["angle"][0].append(
                    self.peak_hist_ax_r.plot(pen=example_utils.pg_pen_cycler(i),
                                             name="Angle {:d}".format(i)))
            if self.hist_plots["distance"][1]:
                self.hist_plots["distance"][0].append(
                    self.peak_hist_ax_l.plot(pen=example_utils.pg_pen_cycler(i),
                                             name="Distance {:d}".format(i)))

        self.smooth_max = example_utils.SmoothMax(
                self.sensor_config.sweep_rate,
                tau_decay=1,
                tau_grow=0.2
                )

    def update(self, data):
        ds = max(self.downsampling, 8)  # downsampling
        nfft = data["fft_map"].shape[1]
        if self.plot_index == 0:
            num_points = data["env_ampl"].size
            self.env_xs = np.linspace(*self.sensor_config.range_interval*100, num_points)
            self.peak_x = self.env_xs[data["peak_idx"]]

            self.obstacle_im.translate(-self.max_velocity, self.sensor_config.range_start*100)
            self.obstacle_im.scale(
                    2*self.max_velocity/nfft,
                    self.sensor_config.range_length*100/num_points*ds
                    )
            if self.advanced_plots["background_map"]:
                self.obstacle_bg_im.translate(-self.max_velocity,
                                              self.sensor_config.range_start*100)
                self.obstacle_bg_im.scale(
                        2*self.max_velocity/nfft,
                        self.sensor_config.range_length*100/num_points*ds
                        )
            if self.advanced_plots["threshold_map"]:
                self.obstacle_thresh_im.translate(-self.max_velocity,
                                                  self.sensor_config.range_start*100)
                self.obstacle_thresh_im.scale(
                        2*self.max_velocity/nfft,
                        self.sensor_config.range_length*100/num_points*ds)
        else:
            self.peak_x = self.peak_x * 0.7 + 0.3 * self.env_xs[data["peak_idx"]]

        peak_dist_text = "Peak: {:.1f}mm".format(self.peak_x)
        peak_fft_text = "No peaks found"

        if data["fft_peaks"] is not None:
            dist = self.env_xs[data["fft_peaks"][:, 0].astype(int)]
            vel = (data["fft_peaks"][:, 1] / data["fft_map"].shape[1] * 2 - 1) * self.max_velocity
            peak_fft_text = "Dist: {:.1f}cm, Speed/Angle: {:.1f}cm/s / {:.0f}".format(
                                dist[0], data["velocity"], data["angle"])

            half_pixel = self.max_velocity / np.floor(data["fft_map"].shape[1] / 2) / 2
            self.obstacle_peak.setData(vel + half_pixel, dist)
        else:
            self.obstacle_peak.setData([], [])

        for i in range(self.nr_locals):
            if self.hist_plots["distance"][1]:
                self.hist_plots["distance"][0][i].setData(data["peak_hist"][i, 0, :],
                                                          connect="finite")
            if self.hist_plots["velocity"][1]:
                self.hist_plots["velocity"][0][i].setData(data["peak_hist"][i, 1, :],
                                                          connect="finite")
            if self.hist_plots["angle"][1]:
                self.hist_plots["angle"][0][i].setData(data["peak_hist"][i, 2, :],
                                                       connect="finite")

        map_max = np.max(np.max(data["fft_map"]))

        self.peak_dist_text.setText(peak_dist_text)
        self.peak_fft_text.setText(peak_fft_text)
        self.peak_val_text.setText("FFT max: %.3f" % map_max)

        self.env_ampl.setData(self.env_xs, data["env_ampl"])
        self.env_peak_vline.setValue(self.peak_x)

        env_max = np.max(data["env_ampl"])
        if data["fft_peaks"] is not None:
            fft_max = np.max(data["fft_max_env"])
            env_max = max(env_max, fft_max)

        self.env_ax.setYRange(0, self.smooth_max.update(env_max))

        self.fft_max.setData(self.env_xs, data["fft_max_env"])

        fft_data = data["fft_map"].T

        g = 1/2.2
        fft_data = 254/(map_max + 1.0e-9)**g * fft_data**g

        fft_data[fft_data > 254] = 254

        map_min = 0
        map_max = 256

        self.obstacle_im.updateImage(fft_data[:, ::ds], levels=(map_min, map_max))

        if data["threshold_map"] is not None and self.advanced_plots["threshold_map"]:
            thresh_max = np.max(data["threshold_map"])
            self.obstacle_thresh_im.updateImage(data["threshold_map"].T, levels=(0, thresh_max))

        if data["fft_bg"] is not None and self.advanced_plots["background_map"]:
            map_max = np.max(np.max(data["fft_bg"]))
            fft_data = data["fft_bg"].T
            fft_data = 254/map_max**g * fft_data**g

            fft_data[fft_data > 254] = 254

            map_min = 0
            map_max = 256

            self.obstacle_bg_im.updateImage(fft_data[:, ::ds], levels=(map_min, map_max))

        self.plot_index += 1


if __name__ == "__main__":
    main()
