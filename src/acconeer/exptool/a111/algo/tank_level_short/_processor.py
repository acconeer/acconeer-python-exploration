# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np
import scipy.signal
import scipy.stats

import acconeer.exptool as et

from .calibration import EnvelopeCalibration


ENVELOPE_BACKGROUND_LEVEL = 100


def get_sensor_config():
    config = et.a111.EnvelopeServiceConfig()
    config.range_interval = [0.0, 0.4]
    config.update_rate = 20
    config.gain = 0.0
    config.profile = config.Profile.PROFILE_1
    config.hw_accelerated_average_samples = 40
    config.running_average_factor = 0  # Use averaging in detector instead of in API
    config.noise_level_normalization = True
    config.maximize_signal_attenuation = False
    config.downsampling_factor = 1

    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 2

    bg_buffer_length = et.configbase.IntParameter(
        default_value=50,
        limits=(1, 200),
        label="Background buffer length",
        order=10,
    )

    history_length_s = et.configbase.IntParameter(
        default_value=10,
        unit="s",
        limits=(10, 1000),
        label="History length",
        order=20,
    )

    smoothing_time_const = et.configbase.FloatParameter(
        label="Smoothing time const.",
        unit="s",
        default_value=0.5,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=30,
        help=("Time constant for the smoothing filter of the normalized raw data."),
    )

    use_masks = et.configbase.BoolParameter(
        label="Use mask system for distance measurement",
        default_value=False,
        updateable=False,
        order=40,
        help=(
            "Whether to use the mask system for distance evaluation. "
            "Otherwise, use a faster, less precise 'naive' measurement."
        ),
    )

    precision = et.configbase.IntParameter(
        default_value=150,
        limits=(1, 2000),
        label="Precision",
        updateable=False,
        order=50,
        help=(
            "Number of possible output values. "
            "High number yields slower performance and finer grain of output."
        ),
    )

    score_threshold = et.configbase.FloatParameter(
        label="Confidence threshold to return a guess.",
        default_value=0.75,
        limits=(0.5, 1.0),
        logscale=True,
        updateable=True,
        order=60,
        help=(
            "Threshold for the similarity measurement to return a value. "
            "Only used when use_masks is active."
        ),
    )

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }

        if not sensor_config.noise_level_normalization:
            alerts["sensor"].append(
                et.configbase.Warning(
                    "noise_level_normalization", "Should be set unless using calibration."
                )
            )

        if (
            sensor_config.profile != sensor_config.Profile.PROFILE_1
            and sensor_config.profile != sensor_config.Profile.PROFILE_2
        ):
            alerts["sensor"].append(et.configbase.Error("profile", "Only profile 1 or 2."))

        if sensor_config.update_rate is None:
            alerts["sensor"].append(et.configbase.Error("update_rate", "Must be set"))

        if (
            sensor_config.profile == sensor_config.Profile.PROFILE_1
            and sensor_config.range_interval[1] > 0.6
        ) or (
            sensor_config.profile == sensor_config.Profile.PROFILE_2
            and sensor_config.range_interval[1] > 0.8
        ):
            alerts["sensor"].append(
                et.configbase.Warning("range_interval", "Long range might yield poor results.")
            )

        if not self.use_masks:
            alerts["processing"].append(et.configbase.Info("precision", "Not used in this mode"))
            alerts["processing"].append(
                et.configbase.Info("score_threshold", "Not used in this mode")
            )

        return alerts


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):

        self.session_info = session_info
        self.sensor_config = sensor_config
        self.processing_config = processing_config

        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.num_sensors = len(sensor_config.sensor)

        self.calibration = calibration
        buffer_length = self.processing_config.bg_buffer_length
        self.bg_buffer = np.zeros([buffer_length, self.num_depths])

        self.range_start = self.session_info["range_start_m"]
        self.range_length = self.session_info["range_length_m"]

        self.data_index = 0

        self.use_masks = processing_config.use_masks

        tc = processing_config.smoothing_time_const
        self.fs = sensor_config.update_rate
        alpha = self.tc_to_sf(tc, self.fs)

        self.history_length_s = processing_config.history_length_s

        self.smooth_const = alpha
        self.smooth_val = np.zeros(self.num_depths)

        self.scale_array = self.depths / max(self.depths)

        if self.use_masks:
            self.score_threshold = processing_config.score_threshold
            self.peak_width = self.get_peak_width(sensor_config)
            self.masks = self.make_mask_list(processing_config.precision)

        self.guess_history = np.zeros(self.history_length_s)
        self.guess_index_history = np.zeros(self.history_length_s)

    def get_peak_width(self, sensor_config):
        profile = sensor_config.profile
        if profile == sensor_config.Profile.PROFILE_1:
            width = 20
        elif profile == sensor_config.Profile.PROFILE_2:
            width = 40
        else:
            raise ValueError("Illegal profile ({}) for this detector".format(profile))
        return width

    def update_processing_config(self, processing_config):
        tc = processing_config.smoothing_time_const
        alpha = self.tc_to_sf(tc, self.fs)
        self.smooth_const = alpha
        self.score_threshold = processing_config.score_threshold

    def tc_to_sf(self, tc, fs):  # time constant to smoothing factor conversion
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def normalize(self, data):
        div = np.amax(data)
        if div != 0.0:
            data = data / div
        return data

    def get_distance(self, index):
        dist = self.range_start + (index / self.num_depths) * self.range_length
        return dist

    def get_index(self, distance):
        index = self.num_depths * (distance - self.range_start) / self.range_length
        return int(round(index))

    def make_peak(self, index, width):
        x = np.arange(self.num_depths)
        vals = scipy.stats.norm.pdf(x, index, width)
        return vals

    def calculate_mask(self, distance):
        mask = np.zeros(self.num_depths)

        n_peaks = 3

        for i in range(n_peaks):
            dist_to_use = (i + 1) * distance
            index = self.get_index(dist_to_use)
            peak = self.make_peak(index, self.peak_width) * (
                (2 / 3) ** i
            )  # The 2/3 is empirically chosen to best match the behaviour in the close range.
            mask = mask + peak

        mask = mask / max(mask)
        mask[mask < 0.001] = 0.0
        return mask

    def make_mask_list(self, n_points):

        mask_dists = np.linspace(self.range_start, self.range_start + self.range_length, n_points)

        masks = [[self.calculate_mask(r), r] for r in mask_dists]

        return masks

    def get_mask_guess(self):

        best_score = -1.0
        guess = 0.0

        for mask, dist in self.masks:
            match = np.minimum(mask, self.smooth_val)
            overlay = np.maximum(mask, self.smooth_val)
            miss = overlay - match
            score = 1.0 - (sum(miss) / self.num_depths)

            if score > best_score:
                best_score = score
                guess = dist

        if best_score < self.score_threshold:  # test if we have a reasonable guess.
            guess = 0.0

        return guess

    def get_naive_guess(self):
        max_val = np.argmax(self.smooth_val)
        guess = self.get_distance(max_val)
        return guess

    def process(self, data, data_info):

        new_calibration = None

        if self.calibration is None:
            if self.data_index < self.bg_buffer.shape[0]:
                self.bg_buffer[self.data_index] = data
            if self.data_index == self.bg_buffer.shape[0] - 1:
                new_calibration = EnvelopeCalibration(self.bg_buffer.mean(axis=0))
            mean = np.ones(self.num_depths) * ENVELOPE_BACKGROUND_LEVEL
            data = np.maximum(0, data - mean)
        else:
            data = np.maximum(0, data - self.calibration.background)

        plot_data = {}
        plot_data["smooth_data"] = np.zeros(data.shape[0])
        plot_data["index"] = self.data_index

        data = data * self.scale_array  # Scale by distance

        data = self.normalize(data)  # Allow for using a set threshold.

        # Necessary since we have normalized noise.
        self.smooth_val = self.smooth_val * self.smooth_const + (1.0 - self.smooth_const) * data

        if self.use_masks:
            guess = self.get_mask_guess()
        else:
            guess = self.get_naive_guess()

        plot_data["best_guess"] = guess

        if self.data_index % self.fs == 0:
            self.guess_history = np.roll(self.guess_history, -1)
            self.guess_history[-1] = guess
            self.guess_index_history = np.roll(self.guess_index_history, -1)
            self.guess_index_history[-1] = self.data_index

        plot_data["guess_hist"] = self.guess_history
        plot_data["guess_hist_idx"] = self.guess_index_history
        plot_data["smooth_data"] = self.smooth_val

        if new_calibration is not None:
            plot_data["new_calibration"] = new_calibration

        self.data_index += 1

        return plot_data

    def update_calibration(self, new_calibration: EnvelopeCalibration):
        self.calibration = new_calibration
        self.data_index = 1
        self.guess_history = np.zeros(self.history_length_s)
        self.guess_index_history = np.zeros(self.history_length_s)
