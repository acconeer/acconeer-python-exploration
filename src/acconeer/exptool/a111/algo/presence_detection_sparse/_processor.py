# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np
from numpy import cos, pi, sqrt, square
from scipy.special import binom

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_3
    config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.B
    config.range_interval = [0.3, 1.3]
    config.update_rate = 80
    config.sweeps_per_frame = 32
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 6

    detection_threshold = et.configbase.FloatParameter(
        label="Detection threshold",
        default_value=1.5,
        limits=(0, 5),
        updateable=True,
        order=0,
        help='Level at which the detector output is considered as "present".',
    )

    inter_frame_fast_cutoff = et.configbase.FloatParameter(
        label="Inter fast cutoff freq.",
        unit="Hz",
        default_value=20.0,
        limits=(1, 100),
        logscale=True,
        updateable=True,
        order=10,
        help=(
            "Cutoff frequency of the low pass filter for the fast filtered sweep mean."
            " No filtering is applied if the cutoff is set over half the frame rate"
            " (Nyquist limit)."
        ),
    )

    inter_frame_slow_cutoff = et.configbase.FloatParameter(
        label="Inter slow cutoff freq.",
        unit="Hz",
        default_value=0.2,
        limits=(0.01, 1),
        logscale=True,
        updateable=True,
        order=20,
        help="Cutoff frequency of the low pass filter for the slow filtered sweep mean.",
    )

    inter_frame_deviation_time_const = et.configbase.FloatParameter(
        label="Inter deviation time const.",
        unit="s",
        default_value=0.5,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=30,
        help=(
            "Time constant of the low pass filter for the (inter-frame) deviation between"
            " fast and slow."
        ),
    )

    intra_frame_time_const = et.configbase.FloatParameter(
        label="Intra time const.",
        unit="s",
        default_value=0.15,
        limits=(0, 0.5),
        updateable=True,
        order=40,
        help="Time constant for the intra frame part.",
    )

    intra_frame_weight = et.configbase.FloatParameter(
        label="Intra weight",
        default_value=0.6,
        limits=(0, 1),
        updateable=True,
        order=50,
        help=(
            "The weight of the intra-frame part in the final output. A value of 1 corresponds"
            " to only using the intra-frame part and a value of 0 corresponds to only using"
            " the inter-frame part."
        ),
    )

    output_time_const = et.configbase.FloatParameter(
        label="Output time const.",
        unit="s",
        default_value=0.5,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=60,
        help="Time constant of the low pass filter for the detector output.",
    )

    num_removed_pc = et.configbase.IntParameter(
        label="PCA based noise reduction",
        default_value=0,
        limits=(0, 2),
        updateable=False,
        order=70,
        help=(
            "Sets the number of principal components removed in the PCA based noise reduction."
            " Filters out static reflections."
            " Setting to 0 (default) disables the PCA based noise reduction completely."
        ),
    )

    show_data = et.configbase.BoolParameter(
        label="Show data scatter plot",
        default_value=True,
        updateable=True,
        order=100,
        help=(
            "Show the plot of the current data frame along with the fast and slow filtered"
            " mean sweep (used in the inter-frame part)."
        ),
    )

    show_noise = et.configbase.BoolParameter(
        label="Show noise",
        default_value=False,
        updateable=True,
        order=110,
        help="Show the noise estimation plot.",
        category=et.configbase.Category.ADVANCED,
    )

    show_depthwise_output = et.configbase.BoolParameter(
        label="Show depthwise presence",
        default_value=True,
        updateable=True,
        order=120,
        help="Show the depthwise presence output plot.",
    )

    show_sectors = et.configbase.BoolParameter(
        label="Show distance sectors",
        default_value=False,
        updateable=True,
        order=130,
    )

    history_plot_ceiling = et.configbase.FloatParameter(
        label="Presence score plot ceiling",
        default_value=10.0,
        decimals=1,
        limits=(1, 100),
        logscale=True,
        updateable=True,
        optional=True,
        optional_label="Fixed",
        order=190,
        help="The highest presence score that will be plotted.",
        category=et.configbase.Category.ADVANCED,
    )

    history_length_s = et.configbase.FloatParameter(
        label="History length",
        unit="s",
        default_value=5,
        limits=(1, 20),
        decimals=0,
        order=200,
        category=et.configbase.Category.ADVANCED,
    )

    def check_sensor_config(self, conf):
        alerts = {
            "processing": [],
            "sensor": [],
        }
        if conf.update_rate is None:
            alerts["sensor"].append(et.configbase.Error("update_rate", "Must be set"))

        if not conf.sweeps_per_frame > 3:
            alerts["sensor"].append(et.configbase.Error("sweeps_per_frame", "Must be > 3"))

        return alerts


class Processor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.f = sensor_config.update_rate
        self.num_removed_pc = processing_config.num_removed_pc

        # Fixed parameters
        self.noise_est_diff_order = 3
        self.depth_filter_length = 3
        noise_tc = 1.0

        assert sensor_config.update_rate is not None
        assert self.sweeps_per_frame > self.noise_est_diff_order

        self.noise_sf = self.tc_to_sf(noise_tc, self.f)

        nd = self.noise_est_diff_order
        self.noise_norm_factor = np.sqrt(np.sum(np.square(binom(nd, np.arange(nd + 1)))))

        self.fast_lp_mean_sweep = np.zeros(self.num_depths)
        self.slow_lp_mean_sweep = np.zeros(self.num_depths)
        self.lp_inter_dev = np.zeros(self.num_depths)
        self.lp_intra_dev = np.zeros(self.num_depths)
        self.lp_noise = np.zeros(self.num_depths)

        if self.num_removed_pc == 0:
            self.noise_base = None
        else:
            self.noise_base = np.ones([self.num_removed_pc, self.num_depths])
            if self.num_removed_pc == 2:
                self.noise_base[1, ::2] = -1

            self.noise_base = self.normalize_noise_base(self.noise_base)

        self.presence_score = 0
        self.presence_distance_index = 0
        self.presence_distance = 0

        self.presence_history = np.zeros(int(round(self.f * processing_config.history_length_s)))
        self.update_index = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.threshold = processing_config.detection_threshold
        self.intra_weight = processing_config.intra_frame_weight
        self.inter_weight = 1.0 - self.intra_weight

        self.fast_sf = self.cutoff_to_sf(processing_config.inter_frame_fast_cutoff, self.f)
        self.slow_sf = self.cutoff_to_sf(processing_config.inter_frame_slow_cutoff, self.f)
        self.inter_dev_sf = self.tc_to_sf(
            processing_config.inter_frame_deviation_time_const, self.f
        )
        self.intra_sf = self.tc_to_sf(processing_config.intra_frame_time_const, self.f)
        self.output_sf = self.tc_to_sf(processing_config.output_time_const, self.f)

    def cutoff_to_sf(self, fc, fs):  # cutoff frequency to smoothing factor conversion
        if fc > 0.5 * fs:
            return 0.0

        cos_w = cos(2.0 * pi * (fc / fs))
        return 2.0 - cos_w - sqrt(square(cos_w) - 4.0 * cos_w + 3.0)

    def tc_to_sf(self, tc, fs):  # time constant to smoothing factor conversion
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.update_index))

    def abs_dev(self, a, axis=None, ddof=0, subtract_mean=True):
        if subtract_mean:
            a = a - a.mean(axis=axis, keepdims=True)

        if axis is None:
            n = a.size
        else:
            n = a.shape[axis]

        assert ddof >= 0
        assert n > ddof

        return np.mean(np.abs(a), axis=axis) * sqrt(n / (n - ddof))

    def depth_filter(self, a):
        b = np.ones(self.depth_filter_length) / self.depth_filter_length

        if a.size >= b.size:
            return np.correlate(a, b, mode="same")
        else:
            pad_width = int(np.ceil((b.size - a.size) / 2))
            a = np.pad(a, pad_width, "constant")
            return np.correlate(a, b, mode="same")[pad_width:-pad_width]

    @staticmethod
    def normalize_noise_base(noise_base):
        norm = np.sqrt(np.sum(np.square(noise_base), axis=1, keepdims=True))
        return noise_base / norm

    def process(self, data, data_info):
        frame = data

        # Noise estimation

        nd = self.noise_est_diff_order

        noise_diff = np.diff(frame, n=nd, axis=0)
        noise = self.abs_dev(noise_diff, axis=0, subtract_mean=False)
        noise /= self.noise_norm_factor
        sf = self.dynamic_sf(self.noise_sf)
        self.lp_noise = sf * self.lp_noise + (1.0 - sf) * noise

        # Intra-frame part

        mean_sweep = frame.mean(axis=0)
        frame_diff = frame - mean_sweep

        if self.num_removed_pc > 0:
            noise_coeffs = frame_diff @ self.noise_base.transpose()
            frame_diff = np.abs(frame_diff) - np.abs(noise_coeffs @ self.noise_base)
            frame_diff = np.maximum(frame_diff, 0)

        sweep_dev = self.abs_dev(frame_diff, axis=0, ddof=1, subtract_mean=False)

        sf = self.dynamic_sf(self.intra_sf)
        self.lp_intra_dev = sf * self.lp_intra_dev + (1.0 - sf) * sweep_dev

        norm_lp_intra_dev = np.divide(
            self.lp_intra_dev,
            self.lp_noise,
            out=np.zeros(self.num_depths),
            where=(self.lp_noise > 1.0),
        )

        intra = self.depth_filter(norm_lp_intra_dev)

        # Inter-frame part

        sf = self.dynamic_sf(self.fast_sf)
        self.fast_lp_mean_sweep = sf * self.fast_lp_mean_sweep + (1.0 - sf) * mean_sweep

        sf = self.dynamic_sf(self.slow_sf)
        self.slow_lp_mean_sweep = sf * self.slow_lp_mean_sweep + (1.0 - sf) * mean_sweep

        inter_diff = self.fast_lp_mean_sweep - self.slow_lp_mean_sweep

        if self.num_removed_pc > 0:
            noise_coeffs = inter_diff @ self.noise_base.transpose()
            inter_diff = np.abs(inter_diff) - np.abs(noise_coeffs @ self.noise_base)
            inter_dev = np.maximum(inter_diff, 0)
        else:
            inter_dev = np.abs(inter_diff)

        sf = self.dynamic_sf(self.inter_dev_sf)
        self.lp_inter_dev = sf * self.lp_inter_dev + (1.0 - sf) * inter_dev

        norm_lp_dev = np.divide(
            self.lp_inter_dev,
            self.lp_noise,
            out=np.zeros_like(self.lp_inter_dev),
            where=(self.lp_noise > 1.0),
        )

        norm_lp_dev *= np.sqrt(self.sweeps_per_frame)

        inter = self.depth_filter(norm_lp_dev)

        # Update the noise base

        if self.num_removed_pc > 0:
            noise_coeffs = self.noise_base @ noise_diff.transpose()
            noise_base_update = noise_coeffs @ noise_diff
            noise_base_update = self.normalize_noise_base(noise_base_update)

            sf = self.dynamic_sf(self.noise_sf)
            self.noise_base = sf * self.noise_base + (1.0 - sf) * noise_base_update
            for i in range(len(self.noise_base)):
                for j in range(i):
                    self.noise_base[i] -= self.noise_base[j] * np.dot(
                        self.noise_base[j], self.noise_base[i]
                    )
                self.noise_base[i] /= np.sqrt(np.sum(np.square(self.noise_base[i])))

        # Detector output

        depthwise_presence = self.inter_weight * inter + self.intra_weight * intra

        max_depthwise_presence = np.max(depthwise_presence)

        sf = self.dynamic_sf(self.output_sf)
        self.presence_score = sf * self.presence_score + (1.0 - sf) * max_depthwise_presence

        presence_detected = self.presence_score > self.threshold

        self.presence_history = np.roll(self.presence_history, -1)
        self.presence_history[-1] = self.presence_score

        if max_depthwise_presence > self.threshold:
            self.presence_distance_index = np.argmax(depthwise_presence)
            self.presence_distance = self.depths[self.presence_distance_index]

        out_data = {
            "frame": frame,
            "fast": self.fast_lp_mean_sweep,
            "slow": self.slow_lp_mean_sweep,
            "noise": self.lp_noise,
            "inter": inter * self.inter_weight,
            "intra": intra * self.intra_weight,
            "depthwise_presence": depthwise_presence,
            "presence_score": self.presence_score,
            "presence_distance_index": self.presence_distance_index,
            "presence_distance": self.presence_distance,
            "presence_history": self.presence_history,
            "presence_detected": presence_detected,
        }

        self.update_index += 1

        return out_data
