import logging
import os

import numpy as np
import yaml
from numpy import pi, unravel_index
from scipy.fftpack import fft, fftshift

import acconeer.exptool as et

from .constants import FUSION_HISTORY, FUSION_MAX_OBSTACLES, FUSION_MAX_SHADOWS, WAVELENGTH


BACKGROUND_PLATEAU_INTERPOLATION = 0.25  # Default plateau for background parameterization
BACKGROUND_PLATEAU_FACTOR = 1.25  # Default factor for background parameterization
MAX_SPEED = 8.00  # Max speed to be resolved with FFT in cm/s


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger(__name__)


def get_sensor_config():
    config = et.configs.IQServiceConfig()
    config.range_interval = [0.1, 0.5]
    config.repetition_mode = et.configs.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    config.update_rate = int(np.ceil(MAX_SPEED * 4 / WAVELENGTH))
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
            "value": 0.05,
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
            "value": 1,
            "limits": [0, 124],
            "type": int,
            "advanced": True,
        },
        "calib": {
            "name": "Background iterations",
            "value": 10,
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
            "value": 45,
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
            "name": "Show background",
            "value": True,
            "advanced": True,
        },
        "threshold_map": {
            "name": "Show threshold map",
            "value": False,
            "advanced": True,
        },
        "show_line_outs": {
            "name": "Show extra line outs",
            "value": False,
            "advanced": True,
        },
        "distance_history": {
            "name": "Show distance history",
            "value": True,
            "advanced": True,
        },
        "velocity_history": {
            "name": "Show velocity history",
            "value": True,
            "advanced": True,
        },
        "angle_history": {
            "name": "Show angle history",
            "value": True,
            "advanced": True,
        },
        "amplitude_history": {
            "name": "Show amplitude history",
            "value": False,
            "advanced": True,
        },
        "fusion_map": {
            "name": "Show fusion (2 sensors)",
            "value": False,
            "advanced": True,
        },
        "show_shadows": {
            "name": "Show shadows",
            "value": False,
            "advanced": True,
        },
        "sensor_separation": {
            "name": "Sensor separation [cm]",
            "value": 15,
            "limits": [1, 100],
            "type": float,
            "advanced": True,
        },
        "fusion_spread": {
            "name": "Fusion spread [degrees]",
            "value": 15,
            "limits": [1, 45],
            "type": float,
            "advanced": True,
        },
        # Allows saving and loading from GUI
        "send_process_data": {
            "value": None,
            "text": "FFT background",
        },
    }


class ObstacleDetectionProcessor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.sweep_index = 0
        self.bg_avg = 0
        self.fusion_max_obstacles = FUSION_MAX_OBSTACLES
        self.fusion_history = FUSION_HISTORY
        self.fusion_max_shadows = FUSION_MAX_SHADOWS

        self.sensor_config = sensor_config
        self.sensor_separation = processing_config["sensor_separation"]["value"]
        self.fusion_spread = processing_config["fusion_spread"]["value"]
        self.fft_len = processing_config["fft_length"]["value"]
        self.threshold = processing_config["threshold"]["value"]
        self.static_threshold = processing_config["static_threshold"]["value"]
        self.static_distance = processing_config["static_distance"]["value"]
        self.close_threshold_addition = processing_config["close_threshold_addition"]["value"]
        self.use_bg = max(processing_config["calib"]["value"], 0)
        self.bg_off = processing_config["bg_offset"]["value"]
        self.saved_bg = processing_config["send_process_data"]["value"]
        self.peak_hist_len = processing_config["peak_hist"]["value"]
        self.nr_locals = processing_config["nr_peaks"]["value"]
        self.static_freq_limit = processing_config["static_freq"]["value"]
        self.static_dist_gradient = processing_config["static_grad"]["value"]
        self.close_dist_limit = processing_config["close_dist"]["value"]
        self.robot_velocity = processing_config["robot_velocity"]["value"]
        self.edge_ratio = processing_config["edge_to_peak"]["value"]
        self.downsampling = processing_config["downsampling"]["value"]
        self.fusion_enabled = processing_config["fusion_map"]["value"]
        self.fusion_handle = None
        self.bg_params = []

    def _load_calibration(self, nr_sensors):
        if not isinstance(self.saved_bg, dict):
            log.warning("Received unsupported background data!")
            return

        try:
            for s in range(nr_sensors):
                # Generate background from piece-wise-linear (pwl) interpolation
                self.bg_params.append(self.saved_bg)
                self.generate_background_from_pwl_params(self.fft_bg[s, :, :], self.saved_bg)
                if s == 0:
                    self.dump_bg_params_to_yaml()
                self.use_bg = False
            log.info("Using saved parameterized FFT background data!")
        except Exception:
            log.warning("Could not reconstruct background!")

    def _first_sweep_setup(self, nr_sensors, len_range):
        if self.fusion_enabled and nr_sensors <= 2:
            self.fusion_handle = SensorFusion()
            fusion_params = {
                "separation": self.sensor_separation,
                "obstacle_spread": self.fusion_spread,
                "min_y_spread": 4,  # cm
                "min_x_spread": 4,  # cm
                "decay_time": 5,  # cycles
                "step_time": 1 / self.sensor_config.update_rate,  # s
                "min_distance": self.sensor_config.range_start * 100,  # cm
            }
            self.fusion_handle.setup(fusion_params)

        self.sweep_map = np.zeros((nr_sensors, len_range, self.fft_len), dtype="complex")
        self.fft_bg = np.zeros((nr_sensors, len_range, self.fft_len))
        self.hamming_map = np.zeros((len_range, self.fft_len))

        self.fusion_data = {
            "fused_y": np.full((self.fusion_history, self.fusion_max_obstacles), np.nan),
            "fused_x": np.full((self.fusion_history, self.fusion_max_obstacles), np.nan),
            "left_shadow_y": np.full((self.fusion_history, self.fusion_max_shadows), np.nan),
            "left_shadow_x": np.full((self.fusion_history, self.fusion_max_shadows), np.nan),
            "right_shadow_y": np.full((self.fusion_history, self.fusion_max_shadows), np.nan),
            "right_shadow_x": np.full((self.fusion_history, self.fusion_max_shadows), np.nan),
        }

        for i in range(len_range):
            self.hamming_map[i, :] = np.hamming(self.fft_len)

        self.env_xs = np.linspace(*self.sensor_config.range_interval * 100, len_range)
        self.peak_prop_num = 4
        self.peak_hist = np.zeros(
            (nr_sensors, self.nr_locals, self.peak_prop_num, self.peak_hist_len)
        )
        self.peak_hist *= float(np.nan)
        self.mask = np.zeros((len_range, self.fft_len))
        self.threshold_map = np.zeros((len_range, self.fft_len))

        if self.saved_bg is not None:
            self._load_calibration(nr_sensors)

        for dist in range(len_range):
            for freq in range(self.fft_len):
                self.threshold_map[dist, freq] = self.variable_thresholding(
                    freq, dist, self.threshold, self.static_threshold
                )

    def _save_calibration(self, nr_sensors):
        for i in range(nr_sensors):
            self.bg_params.append(self.parameterize_bg(self.fft_bg[i, :, :]))
            # only dump first sensor params
            if i == 0:
                self.dump_bg_params_to_yaml()
            self.generate_background_from_pwl_params(self.fft_bg[i, :, :], self.bg_params[i])

    def _process_single_sensor(self, sweep, s, fft_psd, nr_sensors, fused_obstacles):
        self.push(sweep[s, :], self.sweep_map[s, :, :])

        signalFFT = fftshift(fft(self.sweep_map[s, :, :] * self.hamming_map, axis=1), axes=1)
        fft_psd[s, :, :] = np.square(np.abs(signalFFT))
        signalPSD = fft_psd[s, :, :]

        if self.use_bg and self.sweep_index == self.fft_len - 1:
            self.fft_bg[s, :, :] = np.maximum(self.bg_off * signalPSD, self.fft_bg[s, :, :])
            if s == nr_sensors - 1:
                self.bg_avg += 1
                if self.bg_avg == self.use_bg:
                    self._save_calibration(nr_sensors)

        signalPSD_sub = signalPSD - self.fft_bg[s, :, :]
        signalPSD_sub[signalPSD_sub < 0] = 0
        env = np.abs(sweep[s, :])

        fft_peaks, peaks_found = self.find_peaks(signalPSD_sub)
        fft_max_env = signalPSD[:, 8]
        angle = None
        velocity = None
        peak_idx = np.argmax(env)
        obstacles = []

        if self.sweep_index < self.fft_len:
            fft_peaks = None

        if fft_peaks is not None:
            fft_max_env = signalPSD[:, int(fft_peaks[0, 1])]
            zero = np.floor(self.fft_len / 2)

            for i in range(self.nr_locals):
                bin_index = fft_peaks[i, 2] - zero
                velocity = (bin_index / zero) * WAVELENGTH * self.sensor_config.update_rate / 4
                angle = np.arccos(self.clamp(abs(velocity) / self.robot_velocity, -1.0, 1.0))
                angle = np.sign(velocity) * angle / pi * 180
                peak_idx = int(fft_peaks[i, 0])
                distance = self.env_xs[int(fft_peaks[i, 0])]
                amp = fft_peaks[i, 3]

                if not amp:
                    distance = float(np.nan)
                    velocity = float(np.nan)
                    angle = float(np.nan)
                    amp = float(np.nan)
                elif self.fusion_handle:
                    obstacles.append(
                        {
                            "angle": abs(angle),
                            "velocity": velocity,
                            "distance": distance,
                            "amplitude": amp,
                            "sensor": s,
                        }
                    )
                self.push_vec(distance, self.peak_hist[s, i, 0, :])
                self.push_vec(velocity, self.peak_hist[s, i, 1, :])
                self.push_vec(angle, self.peak_hist[s, i, 2, :])
                self.push_vec(amp, self.peak_hist[s, i, 3, :])

            fft_peaks = fft_peaks[:peaks_found, :]
        else:
            for i in range(self.nr_locals):
                for j in range(self.peak_prop_num):
                    self.push_vec(float(np.nan), self.peak_hist[s, i, j, :])
        fused_obstacles["{}".format(s)] = obstacles

        out_data_contrib = {
            "env_ampl": env,
            "fft_max_env": fft_max_env,
            "fft_map": fft_psd,
            "peak_idx": peak_idx,
            "angle": angle,
            "velocity": velocity,
            "fft_peaks": fft_peaks,
            "peak_hist": self.peak_hist[0, :, :, :],
            "sweep_index": self.sweep_index,
            "peaks_found": peaks_found,
        }
        return out_data_contrib

    def process(self, data, data_info):
        sweep = data

        if len(sweep.shape) == 1:
            sweep = np.expand_dims(sweep, 0)

        if self.downsampling:
            sweep = sweep[:, :: self.downsampling]

        sweep = sweep / 2 ** 12

        nr_sensors, len_range = sweep.shape

        nr_sensors = min(len(self.sensor_config.sensor), nr_sensors)

        if self.sweep_index == 0 and self.bg_avg == 0:
            self._first_sweep_setup(nr_sensors, len_range)

        fft_psd = np.empty((nr_sensors, len_range, self.fft_len))
        fused_obstacles = {}
        out_datas = []

        for s in range(nr_sensors):
            out_datas.append(
                self._process_single_sensor(sweep, s, fft_psd, nr_sensors, fused_obstacles)
            )

        if self.fusion_handle:
            fused_obstacles, shadow_obstacles = self.fusion_handle.update(fused_obstacles)

            for position in self.fusion_data:
                self.fusion_data[position] = np.roll(self.fusion_data[position], 1, axis=0)
                self.fusion_data[position][0, :] = np.nan

            if fused_obstacles is not None and nr_sensors == 2:
                for i, o in enumerate(fused_obstacles):
                    if i < self.fusion_max_obstacles:
                        self.fusion_data["fused_x"][0, i] = o["pos"][0]
                        self.fusion_data["fused_y"][0, i] = o["pos"][1]
                    else:
                        print("Too many fused obstacles ({})".format(len(fused_obstacles)))
            if shadow_obstacles is not None:
                for i, o in enumerate(shadow_obstacles):
                    if i < self.fusion_max_shadows:
                        tag = o["sensor"]
                        self.fusion_data["{}_shadow_x".format(tag)][0, i] = o["pos"][0]
                        self.fusion_data["{}_shadow_y".format(tag)][0, i] = o["pos"][1]
                    else:
                        print("Too many shadow obstacles ({})".format(len(shadow_obstacles)))

        fft_bg = None
        fft_bg_send = None
        if self.sweep_index < 3 * self.fft_len:  # Make sure data gets send to plotting
            fft_bg = self.fft_bg[0, :, :]
            fft_bg_send = self.fft_bg

        if self.use_bg:
            iterations_left = self.use_bg - self.bg_avg
        else:
            iterations_left = 0

        threshold_map = None
        if self.sweep_index < 3 * self.fft_len:  # Make sure data gets send to plotting
            threshold_map = self.threshold_map

        f_data = self.fusion_data

        # Only second sensor for dual setup.
        out_data = out_datas[-1]
        out_data.update(
            {
                "fft_bg": fft_bg,
                "fft_bg_iterations_left": iterations_left,
                "threshold_map": threshold_map,
                "send_process_data": fft_bg_send,
                "fused_obstacles": [f_data["fused_x"], f_data["fused_y"]],
                "left_shadows": [f_data["left_shadow_x"], f_data["left_shadow_y"]],
                "right_shadows": [f_data["right_shadow_x"], f_data["right_shadow_y"]],
            }
        )

        if (self.bg_avg < self.use_bg) and (self.sweep_index == self.fft_len - 1):
            self.sweep_index = 0
        else:
            self.sweep_index += 1

        return out_data

    def dump_bg_params_to_yaml(self, filename=None, bg_params=None):
        if filename is None:
            filename = os.path.join(DIR_PATH, "obstacle_bg_params_dump.yaml")

        if bg_params is None:
            bg_params = self.bg_params[0]

        with open(filename, "w") as f_handle:
            yaml.dump(bg_params, f_handle, default_flow_style=False)

    def remap(self, val, x1, x2, y1, y2):
        if x1 == x2:
            return y1
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

    def parameterize_bg(self, fft_bg):
        dist_len = fft_bg.shape[0]

        static_idx = int(self.fft_len / 2)
        adjacent_idx = [int(static_idx - 1), int(static_idx + 1)]
        moving_range = [*range(adjacent_idx[0]), *range(adjacent_idx[1] + 1, self.fft_len)]
        pwl_static_points = 5

        static_pwl_amp = []
        static_pwl_dist = []

        static_sum = 0.0
        adjacent_sum = np.zeros(2)
        moving_sum = 0.0
        moving_sum_sqr = 0.0
        moving_mean_array = np.zeros(dist_len)

        moving_max = 0.0
        moving_min = 0.0

        for dist_index in range(dist_len):
            static_sum += fft_bg[dist_index, static_idx]
            adjacent_sum[0] += fft_bg[dist_index, adjacent_idx[0]]
            adjacent_sum[1] += fft_bg[dist_index, adjacent_idx[1]]

            current_dist_moving_sum = 0.0
            for freq_index in moving_range:
                val = fft_bg[dist_index, freq_index]
                current_dist_moving_sum += val
                if val > moving_max:
                    moving_max = val
                if val < moving_min:
                    moving_min = val
                moving_sum += val
                moving_sum_sqr += val * val

            moving_mean_array[dist_index] = current_dist_moving_sum / len(moving_range)

        segs = self.adapt_background_segment_step(moving_mean_array, dist_len)
        segs_nr = int(len(segs) / 2)
        moving_pwl_dist = segs[0:segs_nr]
        moving_pwl_amp = segs[segs_nr:]

        adjacent_sum_max = max(adjacent_sum)

        if adjacent_sum_max == 0:
            static_adjacent_factor = 0
        else:
            static_adjacent_factor = static_sum / adjacent_sum_max

        bin_width = dist_len / pwl_static_points

        pwl_y_max = 0
        pwl_x_max = 0
        for point_index in range(pwl_static_points):
            dist_begin = int(point_index * bin_width)
            dist_end = int((point_index + 1) * bin_width)

            if point_index == pwl_static_points:
                dist_end = dist_len

            pwl_x_max = 0.0
            pwl_y_max = 0.0
            for dist_index in range(dist_begin, dist_end):
                val = fft_bg[dist_index, static_idx]
                if val > pwl_y_max:
                    pwl_x_max = dist_index
                    pwl_y_max = val

            static_pwl_dist.append(pwl_x_max)
            static_pwl_amp.append(pwl_y_max)

        for i in range(pwl_static_points):
            if static_pwl_amp[i] < moving_max:
                static_pwl_amp[i] = moving_max

        bg_params = {
            "static_pwl_dist": [float(i) for i in static_pwl_dist],
            "static_pwl_amp": [float(i) for i in static_pwl_amp],
            "moving_pwl_dist": [float(i) for i in moving_pwl_dist],
            "moving_pwl_amp": [float(i) for i in moving_pwl_amp],
            "static_adjacent_factor": [float(static_adjacent_factor)],
            "moving_max": [float(moving_max)],
        }

        return bg_params

    def adapt_background_segment_step(self, data_y, data_length):
        mid_index = int(data_length / 2)

        y1 = 0
        for i in range(mid_index):
            if y1 < data_y[i]:
                y1 = data_y[i]

        y2 = 0
        for i in range(mid_index, int(data_length)):
            if y2 < data_y[i]:
                y2 = data_y[i]

        # Check the plateau levels and return early if the step is non-decreasing
        if y1 <= y2:
            y1 = y2
            x1 = 0
            x2 = float(data_length - 1)
            return [x1, x2, y1, y2]

        intersection_threshold = self.remap(BACKGROUND_PLATEAU_INTERPOLATION, 0, 1, y2, y1)
        if intersection_threshold > y2 * BACKGROUND_PLATEAU_FACTOR:
            intersection_threshold = y2 * BACKGROUND_PLATEAU_FACTOR

        intersection_index = mid_index
        while intersection_index > 1 and data_y[intersection_index - 1] < intersection_threshold:
            intersection_index -= 1

        x2 = float(intersection_index)
        y2 = data_y[intersection_index]

        if intersection_index <= 1:
            x1 = 0
            return [x1, x2, y1, y2]

        max_neg_slope = 0
        for i in range(intersection_index):
            neg_slope = (data_y[i] - y2) / float(intersection_index - i)
            if max_neg_slope < neg_slope:
                max_neg_slope = neg_slope
        x1 = x2 - (y1 - y2) / max_neg_slope

        return [x1, x2, y1, y2]

    def generate_background_from_pwl_params(self, fft_bg, bg_params):
        static_idx = int(self.fft_len / 2)
        adjacent_idx = [int(static_idx - 1), int(static_idx + 1)]
        moving_range = [*range(adjacent_idx[0]), *range(adjacent_idx[1] + 1, self.fft_len)]
        pwl_static_points = 5
        pwl_moving_points = 2
        dist_len = fft_bg.shape[0]
        fac = bg_params["static_adjacent_factor"][0]
        static_pwl_amp = bg_params["static_pwl_amp"]
        static_pwl_dist = bg_params["static_pwl_dist"]
        moving_pwl_amp = bg_params["moving_pwl_amp"]
        moving_pwl_dist = bg_params["moving_pwl_dist"]
        moving_max = bg_params["moving_max"][0]

        self.apply_pwl_segments(
            fft_bg, static_idx, static_pwl_dist, static_pwl_amp, pwl_static_points
        )

        for dist_index in range(dist_len):
            static_val = fft_bg[dist_index, 8]
            if static_val < moving_max:
                static_val = moving_max
                fft_bg[dist_index, static_idx] = static_val

            interp_adjacent = moving_max
            if fac > 0:
                interp_adjacent = static_val / fac
                fft_bg[dist_index, adjacent_idx] = interp_adjacent

        for freq_index in moving_range:
            self.apply_pwl_segments(
                fft_bg, freq_index, moving_pwl_dist, moving_pwl_amp, pwl_moving_points
            )

    def apply_pwl_segments(self, fft_bg, freq_index, pwl_dist, pwl_amp, pwl_points):
        dist_len = fft_bg.shape[0]

        x_start = 0
        x_stop = pwl_dist[0]
        y_start = pwl_amp[0]
        y_stop = pwl_amp[0]

        segment_stop = 0
        for dist_index in range(dist_len):
            if x_stop < dist_index:
                x_start = x_stop
                y_start = y_stop
                segment_stop += 1
                if segment_stop < pwl_points:
                    x_stop = pwl_dist[segment_stop]
                    y_stop = pwl_amp[segment_stop]
                else:
                    x_stop = dist_len - 1
            interp = self.remap(dist_index, x_start, x_stop, y_start, y_stop)
            fft_bg[dist_index, freq_index] = interp

    def find_peaks(self, arr):
        if not self.nr_locals:
            return None, 0

        peaks_found = 0
        peak = np.asarray(unravel_index(np.argmax(arr), arr.shape))
        peak_avg = peak[1]

        peak_val = arr[peak[0], peak[1]]
        thresh = self.variable_thresholding(
            peak[1], peak[0], self.threshold, self.static_threshold
        )

        if peak_val < thresh:
            peak = None
            peak_avg = None

        if peak is not None:
            peak_avg = self.calc_peak_avg(peak, arr)
            local_peaks = np.zeros((self.nr_locals, self.peak_prop_num), dtype=float)
            dist_edge = self.edge(arr[:, peak[1]], peak[0], self.edge_ratio)
            local_peaks[0, 0] = dist_edge
            local_peaks[0, 1] = peak[1]
            local_peaks[0, 2] = peak_avg
            local_peaks[0, 3] = np.round(peak_val, decimals=4)
            peaks_found += 1
            self.mask = arr.copy()

            for i in range(self.nr_locals - 1):
                self.peak_masking(local_peaks[i, :])
                p = np.asarray(unravel_index(np.argmax(self.mask), arr.shape))
                thresh = self.variable_thresholding(
                    p[1], p[0], self.threshold, self.static_threshold
                )
                peak_val = arr[p[0], p[1]]
                if peak_val > thresh:
                    dist_edge = self.edge(arr[:, p[1]], p[0], self.edge_ratio)
                    local_peaks[i + 1, 0] = dist_edge
                    local_peaks[i + 1, 1] = p[1]
                    local_peaks[i + 1, 2] = self.calc_peak_avg(p, arr)
                    local_peaks[i + 1, 3] = np.round(peak_val, decimals=4)
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

        distance_start_index = -dist_depth

        if distance_start_index + distance_index < 0:
            distance_start_index = -distance_index

        distance_end_index = dist_depth
        if distance_end_index + distance_index >= dist_len:
            distance_end_index = dist_len - distance_index - 1

        for i in range(-angle_depth, angle_depth + 1):
            wrapped_row = (angle_len + i + angle_index) % angle_len
            for j in range(int(distance_start_index), int(distance_end_index) + 1):
                dist_from_peak = (
                    abs(i) * angle_scaling_per_index + abs(j) * distance_scaling_per_index
                )
                mask_val = (1 - dist_from_peak ** 2) * peak_val * amplitude_margin
                if self.mask[int(j + distance_index), int(wrapped_row)] < mask_val:
                    self.mask[int(j + distance_index), int(wrapped_row)] = 0

    def edge(self, arr, peak_idx, ratio=0.5):
        if ratio == 1.0:
            return peak_idx

        s0 = arr[peak_idx]
        for i in range(peak_idx):
            if peak_idx - i < 0:
                peak_idx = 0
                break
            if arr[peak_idx - i] < s0 * ratio:
                peak_idx -= i
                break

        return peak_idx

    def variable_thresholding(self, freq_index, dist_index, min_thresh, max_thresh):
        dist = self.env_xs[dist_index]
        distance_gradient = self.static_dist_gradient
        thresh = self.remap(
            dist,
            self.static_distance - distance_gradient,
            self.static_distance,
            max_thresh,
            min_thresh,
        )
        thresh = self.clamp(thresh, min_thresh, max_thresh)

        null_frequency = self.fft_len / 2
        frequency_gradient = self.static_freq_limit

        if freq_index <= null_frequency:
            freq = self.clamp(freq_index, null_frequency - frequency_gradient, null_frequency)
            thresh = self.remap(
                freq, null_frequency - frequency_gradient, null_frequency, min_thresh, thresh
            )
        else:
            freq = self.clamp(freq_index, null_frequency, null_frequency + frequency_gradient)
            thresh = self.remap(
                freq, null_frequency, null_frequency + frequency_gradient, thresh, min_thresh
            )

        thresh_add = self.remap(
            dist,
            self.sensor_config.range_start * 100,
            self.sensor_config.range_start * 100 + self.close_dist_limit,
            self.close_threshold_addition,
            0.0,
        )

        thresh += self.clamp(thresh_add, 0, self.close_threshold_addition)

        return thresh


class SensorFusion:
    def __init__(self):
        self.debug = False

        self.iteration = 0

        self.fusion_params = {
            "separation": 15,  # cm
            "obstacle_spread": 10,  # degrees
            "min_y_spread": 2,  # cm
            "min_x_spread": 4,  # cm
            "max_x_spread": 15,  # cm
            "decay_time": 5,  # cycles
            "step_time": 0,  # s
            "min_distance": 6,  # cm
            "use_as_noise_filter": False,  # increases decaytime if known obstacle
        }
        self.fused_obstacles = []

    def setup(self, params):
        for key in params:
            self.fusion_params[key] = params[key]

    def update(self, obstacles):

        right = []
        left = []
        if "0" in obstacles:
            right = obstacles["0"]
        if "1" in obstacles:
            left = obstacles["1"]

        obstacle_list = []

        # Split obstacles into left and right sensor and convert to xy coordinates
        # Each obstavcle has two x and one y coordinate, where x1 is the outer
        # position and x2 is the inner position between both sensors
        for l in left:
            obstacle_list.append(self.convert_to_xy(l, "left"))

        for r in right:
            obstacle_list.append(self.convert_to_xy(r, "right"))

        # create all possible obstacle locations
        shadow_obstacles = self.create_shadow_obstacles(obstacle_list)

        # get updated obstacle data
        new_fused_obstacle_data = self.extract(obstacle_list)

        # combine new obstacles with old obstacles
        self.update_fused_obstacle_data(new_fused_obstacle_data)

        if self.debug:
            self.print_obstacles(obstacle_list, left, right)

        return self.fused_obstacles, shadow_obstacles

    def extract(self, obstacles):
        fused_obstacles = []

        if self.debug:
            self.debug_updates = []

        if len(obstacles) == 0:
            return []

        ref_obst = obstacles[0]
        add_ref = True

        for num, obst in enumerate(obstacles):
            if num == 0:
                continue

            # Check overlap with current obstacle
            overlap_idx, _ = self.check_overlap(ref_obst, obst)
            hist_idx = None
            if overlap_idx:
                self.add_obstacle(
                    fused_obstacles,
                    obst,
                    obst2=ref_obst,
                    idx=overlap_idx,
                    matched=True,
                    position="inner",
                )
                add_ref = False
            else:
                # Check overlap with obstacle history
                overlap_idx, matched, hist_idx = self.check_overlap_with_history(obst)
                if overlap_idx:
                    self.add_obstacle(
                        fused_obstacles,
                        obst,
                        obst2=self.fused_obstacles[hist_idx],
                        idx=overlap_idx,
                        matched=matched,
                        position=self.fused_obstacles[hist_idx]["match_position"],
                        hist_idx=hist_idx,
                    )

            if self.debug:
                if overlap_idx:
                    if hist_idx is None:
                        self.debug_updates.append(
                            "obstacle 0 matched with {} at x{:d}".format(num, overlap_idx)
                        )
                    else:
                        self.debug_updates.append(
                            "obstacle {} matched with fused {} at x{:d}".format(
                                num, hist_idx, overlap_idx
                            )
                        )
                else:
                    self.debug_updates.append("obstacle {} not matched".format(num))

            # If no overlap with old/new obstacle, assume outer position x1
            if overlap_idx is None:
                self.add_obstacle(fused_obstacles, obst, idx=1, position=obst["side"])

        if add_ref:
            # Check ref overlap with obstacle history
            overlap_idx, matched, hist_idx = self.check_overlap_with_history(ref_obst)
            if overlap_idx:
                self.add_obstacle(
                    fused_obstacles,
                    ref_obst,
                    obst2=self.fused_obstacles[hist_idx],
                    idx=overlap_idx,
                    matched=matched,
                    position=self.fused_obstacles[hist_idx]["match_position"],
                    hist_idx=hist_idx,
                )

            else:
                self.add_obstacle(fused_obstacles, ref_obst, idx=1, position=ref_obst["side"])

            if self.debug:
                if overlap_idx:
                    self.debug_updates.append(
                        "obstacle 0 matched with fused {} at x{:d}".format(hist_idx, overlap_idx)
                    )
                else:
                    self.debug_updates.append("obstacle 0 not matched")

        return fused_obstacles

    def check_overlap_with_history(self, obstacle, hist_idx=None):
        overlap_idx = None
        idx = None
        matched = False
        overlaps_matched = []
        overlaps_unmatched = []
        hist = self.fused_obstacles

        if hist_idx:
            hist = [self.fused_obstacles[hist_idx]]

        for idx, o in enumerate(hist):
            # update y spread with prediction
            dy = o["y"][0] - o["predicted"][2]
            y = o["y"] - dy
            y[0] = o["predicted"][2]

            obst_hist = {
                "vec": o["predicted"],
                "x1": o["x1"],
                "x2": o["x1"],
                "y": y,
                "match_position": o["match_position"],
            }

            overlap_idx, d = self.check_overlap(obstacle, obst_hist, mode="history")
            if overlap_idx:
                if o["matched"]:
                    overlaps_matched.append((d[0], overlap_idx, idx))
                else:
                    overlaps_unmatched.append((d[0], overlap_idx, idx))

        over = None
        if len(overlaps_matched):
            over = np.asarray(overlaps_matched)
            matched = True
        elif len(overlaps_unmatched):
            over = np.asarray(overlaps_unmatched)

        if over is not None:
            overlap_idx = int(over[np.argmin(over[:, 0]), 1])
            idx = int(over[np.argmin(over[:, 0]), 2])

        if hist_idx is None:
            hist_idx = idx

        return overlap_idx, matched, hist_idx

    def check_overlap(self, obst1, obst2, mode="current"):
        overlap_idx = None
        delta = None
        o1_x_spread = np.asarray(((obst1["x1"][1:]), (obst1["x2"][1:])))
        o1_y_spread = np.asarray((obst1["y"][1:]))

        o2_y_spread = np.asarray(np.flip(obst2["y"][1:]))
        o2_x_spread = np.asarray((np.flip(obst2["x1"][1:]), np.flip(obst2["x2"][1:])))

        # if there is a sign flip between the outer cooridnate margins, obstacles overlap
        diff_y = o1_y_spread - o2_y_spread

        if np.sign(diff_y[0]) == np.sign(diff_y[1]):
            # No overlap in y
            if not (obst1["y"] == obst2["y"]).any():
                return overlap_idx, delta

        diff_x1 = o1_x_spread[0] - o2_x_spread[0]
        diff_x2 = o1_x_spread[1] - o2_x_spread[1]

        # Overlap in x 1 (outer position)
        if np.sign(diff_x1[0]) != np.sign(diff_x1[1]):
            overlap_idx = 1
        if (obst1["x1"] == obst2["x1"]).any():
            overlap_idx = 1

        # Overlap in x2 (inner position)
        if np.sign(diff_x2[0]) != np.sign(diff_x2[1]):
            overlap_idx = 2
        if (obst1["x2"] == obst2["x2"]).any():
            overlap_idx = 1

        if obst1.get("side") and mode == "history":
            if obst2["match_position"] == "inner" and overlap_idx == 1:
                overlap_idx = None
            if obst2["match_position"] == "left" and obst1["side"] == "right":
                overlap_idx = None
            if obst2["match_position"] == "right" and obst1["side"] == "left":
                overlap_idx = None

        delta = [min(min(abs(diff_x1)), min(abs(diff_x2))), min(abs(diff_y))]

        return overlap_idx, delta

    def update_fused_obstacle_data(self, new_obstacles):
        # compare new obstacles against old obstacles
        no_match_found = np.full(len(self.fused_obstacles), True)
        add_as_new = np.full(len(new_obstacles), False)

        overlaps = []
        for idx_new, new in enumerate(new_obstacles):
            if new["matched_hist_idx"]:
                overlap, matched, idx_old = self.check_overlap_with_history(
                    new, new["matched_hist_idx"]
                )
            else:
                overlap, matched, idx_old = self.check_overlap_with_history(new)
            if overlap:
                overlaps.append((idx_new, idx_old, overlap, matched))
            else:
                add_as_new[idx_new] = True

        for o in overlaps:
            # update old obstacles with new obstacle coordinates
            idx_new = o[0]
            idx_fused = o[1]
            self.update_fused_obstacle(idx_fused, new_obstacles[idx_new], idx_new)
            no_match_found[idx_fused] = False

        # add new obstacles not matching any old obstacles
        for idx, add in enumerate(add_as_new):
            if add:
                self.create_fused_obstacle(new_obstacles[idx])

        # update prediction for unmatched old obstacles and destroy if decayed
        self.decay_fused_obstacles()

        # TODO: remove obstacles we know are not correct
        self.destroy_shadows()

        return

    def decay_fused_obstacles(self):
        for fused_obst in self.fused_obstacles:
            if not fused_obst["updated"]:
                fused_obst["decay_time"] -= 1
                fused_obst["predicted"] = self.predict(fused_obst["vec"])

        for idx, fused_obst in enumerate(self.fused_obstacles):
            if fused_obst["decay_time"] < 1:
                self.fused_obstacles.pop(idx)

        for fused_obst in self.fused_obstacles:
            fused_obst["updated"] = False

    def update_fused_obstacle(self, fused_idx, new_obst_data, idx_new):
        decay_time = self.fusion_params["decay_time"]
        fused_obst = self.fused_obstacles[fused_idx]
        for key in new_obst_data:
            fused_obst[key] = new_obst_data[key]

        if self.fusion_params["use_as_noise_filter"]:
            fused_obst["decay_time"] = min(fused_obst["decay_time"] + 1, decay_time * 2)
        else:
            fused_obst["decay_time"] = min(fused_obst["decay_time"] + 1, decay_time)

        fused_obst["predicted"] = self.predict(new_obst_data["vec"])
        fused_obst["updated"] = True

        if self.debug:
            self.debug_updates.append(
                "updating fused obstacle {} with new obstacle {}".format(fused_idx, idx_new)
            )

    def create_fused_obstacle(self, obst_data):
        if obst_data:
            new_fused = {
                "predicted": self.predict(obst_data["vec"]),
                "decay_time": self.fusion_params["decay_time"],
                "updated": True,
            }
            for key in obst_data:
                new_fused[key] = obst_data[key]
            self.fused_obstacles.append(new_fused)

            if self.debug:
                self.debug_updates.append(
                    "creating new obstacle X/Y {:.1f} / {:.1f}".format(
                        obst_data["pos"][0], obst_data["pos"][1]
                    )
                )

    def destroy_shadows(self):
        pass

    def create_shadow_obstacles(self, obstacle_data):
        shadow_obstacles = []
        for obst in obstacle_data:
            self.add_obstacle(shadow_obstacles, obst, idx=1, matched=False)
            self.add_obstacle(shadow_obstacles, obst, idx=2, matched=False)

        return shadow_obstacles

    def predict(self, vec):
        step_time = self.fusion_params["step_time"]

        predicted = vec.copy()

        vy = vec[4]
        y = vec[2]

        predicted[2] = y + vy * step_time

        return predicted

    def add_obstacle(
        self, o_list, obst1, obst2=None, idx=None, matched=False, position=None, hist_idx=None
    ):
        if idx is None:
            print("Warning: no index for obstacle")
            return
        idx -= 1

        idx_excluded = 0
        if idx == 0:
            idx_excluded = 1

        vec1 = obst1["vec"]
        vec2 = vec1
        if obst2 is not None:
            vec2 = obst2["vec"]

        vec = np.empty_like(vec1)

        amp1 = 1
        amp2 = 1

        # write x coordinate as average of both inputs
        vec[0] = (vec1[idx] * amp1 + vec2[idx] * amp2) / (amp1 + amp2)
        vec[1] = vec[0]

        # write remaining params as average of both inputs
        for i in range(2, len(vec1)):
            vec[i] = (vec1[i] * amp1 + vec2[i] * amp2) / (amp1 + amp2)

        # use angle of obstacle 1
        vec[5] = vec1[5]

        # use closest y distance
        vec[2] = min(vec1[2], vec2[2])

        spread = self.fusion_params["obstacle_spread"]
        fused_angle = np.arctan(vec[0] / vec[2]) / np.pi * 180

        dx1 = np.tan((fused_angle - spread) / 180 * np.pi) * vec[2]
        dx2 = np.tan((fused_angle + spread) / 180 * np.pi) * vec[2]

        fused_x = np.asarray((vec[0], min(dx1, dx2), max(dx1, dx2)))

        max_x_spread = self.fusion_params["max_x_spread"]
        if abs(fused_x[0] - fused_x[1]) > max_x_spread:
            fused_x[1] = fused_x[0] - max_x_spread
        if abs(fused_x[0] - fused_x[2]) > max_x_spread:
            fused_x[2] = fused_x[0] + max_x_spread

        vec[0:6] = np.round(vec[0:6], 1)
        obstacle = {
            "pos": np.round((vec[0], vec[2]), 1),
            "fused_angle": np.round(fused_angle, 1),
            "amplitude": max(vec1[6], vec2[6]),
            "x1": np.round(fused_x, 1),
            "x2": np.round(fused_x, 1),
            "y": np.round(obst1["y"], 1),
            "excluded": np.round((vec1[idx_excluded], vec2[idx_excluded]), 1),
            "vec": vec,
            "matched": matched,
            "match_position": position,
            "matched_hist_idx": hist_idx,
            "sensor": obst1["side"],
        }

        o_list.append(obstacle)

    def convert_to_xy(self, data, side):
        spread = self.fusion_params["obstacle_spread"]
        min_x_spread = self.fusion_params["min_x_spread"]
        min_y_spread = self.fusion_params["min_y_spread"]
        angle = data["angle"]
        distance = data["distance"]
        v = data["velocity"]

        # each coordinate has a margin given by the obstacle spread
        a = np.asarray(
            (
                angle / 180 * np.pi,
                max(angle - spread, 0) / 180 * np.pi,
                max(angle + spread, 0) / 180 * np.pi,
            )
        )

        x = np.sin(a) * distance
        y = np.cos(a) * distance

        y[0] = max(y[0], self.fusion_params["min_distance"])

        vt = np.sin(angle / 180 * np.pi) * v
        vy = -np.cos(angle / 180 * np.pi) * v

        # x1 is outer position for each sensor side
        # x2 is inner postion between both sensors
        x1 = self.fusion_params["separation"] / 2 + x
        x2 = self.fusion_params["separation"] / 2 - x

        if side == "left":
            x1 *= -1
            x2 *= -1

        # make sure coordinates are ordered from left to right
        if x1[1] > x1[2]:
            x1[1:] = np.flip(x1[1:])
        if x2[1] > x2[2]:
            x2[1:] = np.flip(x2[1:])
        if y[1] > y[2]:
            y[1:] = np.flip(y[1:])

        if abs(x1[0] - x1[1]) < min_x_spread:
            x1[1] = x1[0] - min_x_spread
        if abs(x1[0] - x1[2]) < min_x_spread:
            x1[2] = x1[0] + min_x_spread
        if abs(x2[0] - x2[1]) < min_x_spread:
            x2[1] = x2[0] - min_x_spread
        if abs(x2[0] - x2[2]) < min_x_spread:
            x2[2] = x2[0] + min_x_spread

        if abs(y[0] - y[1]) < min_y_spread:
            y[1] = y[0] - min_y_spread
        if abs(y[0] - y[2]) < min_y_spread:
            y[2] = y[0] + min_y_spread

        data["x1"] = np.round(x1, 1)
        data["x2"] = np.round(x2, 1)
        data["vx"] = np.round(vt, 1)
        data["vy"] = np.round(vy, 1)
        data["y"] = np.round(y, 1)
        data["side"] = side
        data["vec"] = np.asarray(
            (
                x1[0],
                x2[0],
                y[0],
                vt,
                vy,
                data["angle"],
                data["amplitude"],
                distance,
                v,
            )
        )
        data["vec"][0:6] = np.round(data["vec"][0:6], 1)

        return data

    def print_obstacles(self, obstacle_list, left, right):
        self.iteration += 1

        print(self.iteration)
        if len(self.fused_obstacles) == 0:
            print("No obstacles!")
        else:
            print("New obstacles:")
        for i, o in enumerate(obstacle_list):
            fmt = (
                "{}: X {:.1f}({:.1f}>{:.1f})/{:.2f}({:.2}>{:.1f})"
                "Y {:.1f}/({:.1f}>{:.1f}) true {:.1f} a {:.1f}"
            )
            print(
                fmt.format(
                    i,
                    o["vec"][0],
                    o["x1"][1],
                    o["x1"][2],
                    o["vec"][1],
                    o["x2"][1],
                    o["x2"][2],
                    o["vec"][2],
                    o["y"][1],
                    o["y"][2],
                    o["distance"],
                    o["vec"][5],
                )
            )

        for update in self.debug_updates:
            print(update)

        if len(self.fused_obstacles):
            print("Fused obstalces (L:{}/R:{} ):".format(len(left), len(right)))
        else:
            print("No fused obstalces!")
        for i, o in enumerate(self.fused_obstacles):
            print(
                "{}: X {:.1f}({:.1f}/{:.2}) Y {:.1f}({:.1f}/{:.1f}) t {} matched {} {}".format(
                    i,
                    o["vec"][0],
                    o["x1"][1],
                    o["x1"][2],
                    o["vec"][2],
                    o["y"][1],
                    o["y"][2],
                    o["decay_time"],
                    o["matched"],
                    o["match_position"],
                )
            )
        print("")
