# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import copy
import logging
import os
from typing import Optional

import attrs
import numpy as np
from numpy import pi, unravel_index
from scipy.fftpack import fft, fftshift

import acconeer.exptool as et

from .calibration import ObstacleDetectionCalibration
from .constants import WAVELENGTH


BACKGROUND_PLATEAU_INTERPOLATION = 0.25  # Default plateau for background parameterization
BACKGROUND_PLATEAU_FACTOR = 1.25  # Default factor for background parameterization
MAX_SPEED = 8.00  # Max speed to be resolved with FFT in cm/s


DIR_PATH = os.path.dirname(os.path.realpath(__file__))
log = logging.getLogger(__name__)


def get_sensor_config():
    config = et.a111.IQServiceConfig()
    config.range_interval = [0.1, 0.5]
    config.repetition_mode = et.a111.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    config.update_rate = int(np.ceil(MAX_SPEED * 4 / WAVELENGTH))
    config.gain = 0.7
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    fft_length = et.configbase.IntParameter(label="FFT length", default_value=16, limits=(2, 512))

    threshold = et.configbase.FloatParameter(
        # Ignore data below threshold in FFT window for moving objects
        label="Moving Threshold",
        default_value=0.05,
        limits=(0, 100),
        decimals=2,
        order=0,
    )

    downsampling = et.configbase.IntParameter(
        label="Downsample scale",
        default_value=1,
        limits=(0, 124),
        category=et.configbase.Category.ADVANCED,
        order=10,
    )

    calib = et.configbase.IntParameter(
        label="Background iterations",
        default_value=10,
        limits=(1, 1000),
        category=et.configbase.Category.ADVANCED,
        order=20,
    )

    bg_offset = et.configbase.FloatParameter(
        label="Background Scale",
        default_value=1.6,
        limits=(0, 1000),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=30,
    )

    static_threshold = et.configbase.FloatParameter(
        label="Stationary Threshold",
        default_value=0.1,
        limits=(0.0, 100),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=40,
    )

    close_threshold_addition = et.configbase.FloatParameter(
        # Ignore data below threshold for very close range
        label="Close Threshold Addition",
        default_value=0.1,
        limits=(0.0, 100),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=50,
    )

    static_distance = et.configbase.FloatParameter(
        label="Distance limit far",
        default_value=45,
        limits=(0.0, 1000),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=60,
    )

    static_grad = et.configbase.FloatParameter(
        label="Static distance gradient",
        default_value=6,
        limits=(0.0, 100),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=70,
    )

    close_dist = et.configbase.FloatParameter(
        label="Distance limit near",
        default_value=16,
        limits=(0.0, 100),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=80,
    )

    static_freq = et.configbase.FloatParameter(
        label="Static frequency gradient",
        default_value=2,
        limits=(0.0, 100),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=90,
    )

    nr_peaks = et.configbase.IntParameter(
        label="Number of peaks",
        default_value=1,
        limits=(0, 100),
        category=et.configbase.Category.ADVANCED,
        order=100,
    )

    edge_to_peak = et.configbase.FloatParameter(
        label="Edge to peak ratio",
        default_value=1,
        limits=(0.0, 1),
        decimals=1,
        category=et.configbase.Category.ADVANCED,
        order=110,
    )

    peak_hist = et.configbase.IntParameter(
        label="Peak history",
        default_value=500,
        limits=(50, 2000),
        category=et.configbase.Category.ADVANCED,
        order=120,
    )

    robot_velocity = et.configbase.FloatParameter(
        label="Robot Velocity",
        unit="cm/s",
        default_value=6,
        limits=(-1000, 1000),
        category=et.configbase.Category.ADVANCED,
        order=130,
    )

    use_parameterization = et.configbase.BoolParameter(
        label="Use bg parameterization",
        default_value=False,
        category=et.configbase.Category.ADVANCED,
        order=140,
    )

    background_map = et.configbase.BoolParameter(
        label="Show background",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=150,
    )

    threshold_map = et.configbase.BoolParameter(
        label="Show threshold map",
        default_value=False,
        category=et.configbase.Category.ADVANCED,
        order=160,
    )

    show_line_outs = et.configbase.BoolParameter(
        label="Show extra line outs",
        default_value=False,
        category=et.configbase.Category.ADVANCED,
        order=170,
    )

    distance_history = et.configbase.BoolParameter(
        label="Show distance history",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=180,
    )

    velocity_history = et.configbase.BoolParameter(
        label="Show velocity history",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=190,
    )

    angle_history = et.configbase.BoolParameter(
        label="Show angle history",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=200,
    )

    distance_history = et.configbase.BoolParameter(
        label="Show distance history",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=210,
    )

    amplitude_history = et.configbase.BoolParameter(
        label="Show amplitude history",
        default_value=True,
        category=et.configbase.Category.ADVANCED,
        order=220,
    )

    sensor_separation = et.configbase.FloatParameter(
        label="Sensor separation",
        unit="cm",
        default_value=15,
        limits=(1, 100),
        category=et.configbase.Category.ADVANCED,
        order=230,
    )


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.sweep_index = 0

        self.sensor_config = sensor_config

        self.sensor_separation = processing_config.sensor_separation
        self.fft_len = processing_config.fft_length
        self.threshold = processing_config.threshold
        self.static_threshold = processing_config.static_threshold
        self.static_distance = processing_config.static_distance
        self.close_threshold_addition = processing_config.close_threshold_addition
        self.calibration_iterations_left = max(processing_config.calib, 0)
        self.calibration_iterations = self.calibration_iterations_left
        self.peak_hist_len = processing_config.peak_hist
        self.bg_off = processing_config.bg_offset
        self.nr_locals = processing_config.nr_peaks
        self.static_freq_limit = processing_config.static_freq
        self.static_dist_gradient = processing_config.static_grad
        self.close_dist_limit = processing_config.close_dist
        self.robot_velocity = processing_config.robot_velocity
        self.edge_ratio = processing_config.edge_to_peak
        self.downsampling = processing_config.downsampling

        self.len_range = session_info["data_length"]
        self._reset_calculation_arrays(self.len_range)

        if calibration is not None:
            self.update_calibration(calibration)

    def update_calibration(self, calibration: Optional[ObstacleDetectionCalibration]):
        """
        Updates the calibration of processor

        `calibration=None` is expected to remove the calibration from the processor

        Calibration will not truly change until `process` is called.
        """
        if calibration is None:
            self._reset_calibration()
            return

        calib_bg_params = attrs.asdict(copy.deepcopy(calibration))
        calib_bg_params["moving_max"] = [calib_bg_params["moving_max"]]
        calib_bg_params["static_adjacent_factor"] = [calib_bg_params["static_adjacent_factor"]]

        self._apply_calibration(calib_bg_params)

    def _reset_calibration(self):
        """
        Will cause `self` to enter `_first_sweep_setup` on the next `process`-call,
        which will reset most of the state.
        A new calibration will then begin since `self.bg_avg` and `self.sweep_index` is set to 0.
        """
        self.sweep_index = 0
        self.calibration_iterations_left = self.calibration_iterations
        self.is_calibrated = False
        self._reset_calculation_arrays(self.len_range)

    def _apply_calibration(self, parameterized_calibration):
        """
        Will populate self.fft_bg with a "raw" background that is calculated
        from the passed parameterization.
        """
        if not isinstance(parameterized_calibration, dict):
            log.warning("Received unsupported background data!")
            return

        try:
            # Generate background from piece-wise-linear (pwl) interpolation
            self.generate_background_from_pwl_params(
                self.fft_bg[0, :, :], parameterized_calibration
            )
            self.calibration_iterations_left = 0
            self.is_calibrated = True
            log.info("Using saved parameterized FFT background data!")
        except Exception:
            log.warning("Could not reconstruct background!")

    def _reset_calculation_arrays(self, len_range):
        """Resets all arrays used for calculations. This was done on first sweep before."""
        self.sweep_map = np.zeros((1, len_range, self.fft_len), dtype="complex")
        self.fft_bg = np.zeros((1, len_range, self.fft_len))
        self.hamming_map = np.zeros((len_range, self.fft_len))

        for i in range(len_range):
            self.hamming_map[i, :] = np.hamming(self.fft_len)

        self.env_xs = np.linspace(*self.sensor_config.range_interval * 100, len_range)
        self.peak_prop_num = 4
        self.peak_hist = np.zeros((1, self.nr_locals, self.peak_prop_num, self.peak_hist_len))
        self.peak_hist *= float(np.nan)
        self.mask = np.zeros((len_range, self.fft_len))
        self.threshold_map = np.zeros((len_range, self.fft_len))

        for dist in range(len_range):
            for freq in range(self.fft_len):
                self.threshold_map[dist, freq] = self.variable_thresholding(
                    freq, dist, self.threshold, self.static_threshold
                )

    def _process_single_sensor(self, sweep, fft_psd):
        self.push(sweep[0, :], self.sweep_map[0, :, :])

        signalFFT = fftshift(fft(self.sweep_map[0, :, :] * self.hamming_map, axis=1), axes=1)
        fft_psd[0, :, :] = np.square(np.abs(signalFFT))
        signalPSD = fft_psd[0, :, :]

        out_data = {}

        if self.calibration_iterations_left > 0 and self.sweep_index == self.fft_len - 1:
            self.fft_bg[0, :, :] = np.maximum(self.bg_off * signalPSD, self.fft_bg[0, :, :])
            self.calibration_iterations_left -= 1
            if self.calibration_iterations_left == 0:
                bg_params = self.parameterize_bg(self.fft_bg[0, :, :])
                out_data["new_calibration"] = ObstacleDetectionCalibration(**bg_params)

        signalPSD_sub = signalPSD - self.fft_bg[0, :, :]
        signalPSD_sub[signalPSD_sub < 0] = 0
        env = np.abs(sweep[0, :])

        fft_peaks, peaks_found = self.find_peaks(signalPSD_sub)
        fft_max_env = signalPSD[:, 8]
        angle = None
        velocity = None
        peak_idx = np.argmax(env)

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

                self.push_vec(distance, self.peak_hist[0, i, 0, :])
                self.push_vec(velocity, self.peak_hist[0, i, 1, :])
                self.push_vec(angle, self.peak_hist[0, i, 2, :])
                self.push_vec(amp, self.peak_hist[0, i, 3, :])

            fft_peaks = fft_peaks[:peaks_found, :]
        else:
            for i in range(self.nr_locals):
                for j in range(self.peak_prop_num):
                    self.push_vec(float(np.nan), self.peak_hist[0, i, j, :])

        out_data.update(
            {
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
        )
        return out_data

    def process(self, data, data_info):
        sweep = data

        if len(sweep.shape) == 1:
            sweep = np.expand_dims(sweep, 0)

        if self.downsampling:
            sweep = sweep[:, :: self.downsampling]

        sweep = sweep / 2**12

        _, len_range = sweep.shape

        fft_psd = np.empty((1, len_range, self.fft_len))

        out_data = self._process_single_sensor(sweep, fft_psd)

        fft_bg = None
        fft_bg_send = None
        if self.sweep_index < 3 * self.fft_len:  # Make sure data gets send to ui
            fft_bg = self.fft_bg[0, :, :]
            fft_bg_send = self.fft_bg

        threshold_map = None
        if self.sweep_index < 3 * self.fft_len:  # Make sure data gets send to ui
            threshold_map = self.threshold_map

        out_data.update(
            {
                "fft_bg": fft_bg,
                "fft_bg_iterations_left": self.calibration_iterations_left,
                "threshold_map": threshold_map,
                "send_process_data": fft_bg_send,
            }
        )

        if self.calibration_iterations_left > 0 and self.sweep_index == self.fft_len - 1:
            self.sweep_index = 0
        else:
            self.sweep_index += 1

        return out_data

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
                mask_val = (1 - dist_from_peak**2) * peak_val * amplitude_margin
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
