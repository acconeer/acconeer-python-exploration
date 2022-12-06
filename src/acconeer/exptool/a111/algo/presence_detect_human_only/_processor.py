# Copyright (c) Acconeer AB, 2023
# All rights reserved

import numpy as np

import acconeer.exptool as et
from acconeer.exptool.a111.algo import presence_detection_sparse


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_3
    config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.B
    config.range_interval = [0.18, 1.5]
    config.update_rate = 40
    config.sweeps_per_frame = 32
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    slow_motion_threshold = et.configbase.FloatParameter(
        label="Slow motion threshold",
        default_value=2,
        limits=(0, 5),
        updateable=True,
        order=0,
        help=('Level at which the slow motion detection is considered as "Slow motion".'),
    )

    slow_motion_hf_cutoff = et.configbase.FloatParameter(
        label="Slow motion high cutoff freq.",
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

    slow_motion_lf_cutoff = et.configbase.FloatParameter(
        label="Slow motion low cutoff freq.",
        unit="Hz",
        default_value=0.2,
        limits=(0.01, 1),
        logscale=True,
        updateable=True,
        order=20,
        help="Cutoff frequency of the low pass filter for the slow filtered sweep mean.",
    )

    slow_motion_deviation_time_const = et.configbase.FloatParameter(
        label="Slow motion deviation time const.",
        unit="s",
        default_value=3,
        limits=(0.01, 30),
        logscale=True,
        updateable=True,
        order=30,
        help=(
            "Time constant of the low pass filter for the (slow-motion) deviation between"
            " fast and slow."
        ),
    )

    fast_motion_threshold = et.configbase.FloatParameter(
        label="Fast motion threshold",
        default_value=1.4,
        limits=(0, 2),
        updateable=True,
        order=40,
        help=('Level at which the fast motion detection is considered as "Fast motion".'),
    )

    fast_motion_time_const = et.configbase.FloatParameter(
        label="Fast motion time const.",
        unit="s",
        default_value=0.5,
        limits=(0, 0.5),
        updateable=True,
        order=50,
        help="Time constant for the fast motion part.",
    )

    fast_motion_outlier = et.configbase.BoolParameter(
        label="Fast motion outlier detection",
        default_value=False,
        updateable=True,
        order=60,
        help=(
            "Fast motion detection includes outlier detection to optimize detection in"
            " (i.e.) meeting room."
        ),
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
            " mean sweep (used in the slow-motion part)."
        ),
    )

    show_slow = et.configbase.BoolParameter(
        label="Show slow motion",
        default_value=True,
        updateable=True,
        order=110,
        help="Show the slow motion plot.",
        category=et.configbase.Category.ADVANCED,
    )

    show_fast = et.configbase.BoolParameter(
        label="Show fast motion",
        default_value=True,
        updateable=True,
        order=115,
        help="Show the fast motion plot.",
        category=et.configbase.Category.ADVANCED,
    )

    adaptive_threshold = et.configbase.BoolParameter(
        label="Adaptive threshold",
        default_value=True,
        updateable=False,
        order=120,
        help="Changes the threshold array based on the slow and fast motion processing",
        category=et.configbase.Category.ADVANCED,
    )

    show_sectors = et.configbase.BoolParameter(
        label="Show distance sectors",
        default_value=False,
        updateable=True,
        order=130,
    )

    fast_guard_s = et.configbase.FloatParameter(
        label="Fast motion guard interval [s]",
        default_value=160,
        limits=(30, 2000),
        updateable=False,
        order=140,
        help=(
            "Recording time/period in seconds where there should be no fast"
            " motion in the recording period. It records the maximum slow motion threshold"
            " as a new threshold."
        ),
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
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):

        # Config of the presence detector
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.num_depths = self.depths.size
        self.f = sensor_config.update_rate
        self.fast_weight = 0.5
        self.slow_weight = 1.0 - self.fast_weight
        self.presence_config = presence_detection_sparse.ProcessingConfiguration()
        self.presence_config.intra_frame_weight = self.fast_weight
        self.presence_config.num_removed_pc = processing_config.num_removed_pc
        self.presence_detector = presence_detection_sparse.Processor(
            sensor_config, self.presence_config, session_info
        )
        self.presence_distance_index = 0
        self.presence_distance = 0
        self.information = "no_motion"
        self.presence_score_depth = np.zeros(self.num_depths)
        self.human_window_end_index = 0
        self.fls_pos_window_s = 3
        self.fls_neg_window_s = 0.6
        self.Qfactor = 3
        self.percentage_quar1 = 25
        self.percentage_quar3 = 75
        self.InterQuar_no_human = 0.15
        self.cal_state = True
        self.fast_outlier_detected = False
        self.start_cal_index = 0
        self.fast_guard_s = processing_config.fast_guard_s
        self.adaptive_threshold = processing_config.adaptive_threshold
        self.fast_outliers_window_s = 20
        self.fast_outliers = np.linspace(
            1,
            processing_config.fast_motion_threshold,
            num=int(np.ceil(self.fast_outliers_window_s * self.f)),
        )
        self.fls_pos_frame = np.zeros(int(np.ceil(self.fls_pos_window_s * self.f)))
        self.fls_neg_frame = np.zeros(int(np.ceil(self.fls_neg_window_s * self.f)))
        self.slow_history = np.zeros(int(round(self.f * processing_config.history_length_s)))
        self.fast_history = np.zeros(int(round(self.f * processing_config.history_length_s)))
        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.human_window_s = 5 * processing_config.slow_motion_deviation_time_const
        self.cal_window_s = self.fast_guard_s - self.human_window_s
        self.end_cal_index = self.start_cal_index + self.cal_window_s * self.f
        self.fast_motion_threshold = processing_config.fast_motion_threshold
        self.slow_motion_threshold = processing_config.slow_motion_threshold
        self.threshold_stored = np.ones(self.num_depths) * self.slow_motion_threshold
        self.threshold_array = np.ones(self.num_depths) * self.slow_motion_threshold
        self.fast_motion_outlier = processing_config.fast_motion_outlier
        self.presence_config.inter_frame_fast_cutoff = processing_config.slow_motion_hf_cutoff
        self.presence_config.inter_frame_slow_cutoff = processing_config.slow_motion_lf_cutoff
        self.presence_config.inter_frame_deviation_time_const = (
            processing_config.slow_motion_deviation_time_const
        )
        self.presence_config.intra_frame_time_const = processing_config.fast_motion_time_const
        self.presence_detector.update_processing_config(self.presence_config)

    def process(self, data, data_info):
        presence_result = self.presence_detector.process(data, data_info)
        fast_motion = presence_result["intra"] / self.fast_weight
        slow_motion = presence_result["inter"] / self.slow_weight

        # Fast Motion Detector
        max_fast = np.max(fast_motion)
        self.fast_outliers = np.roll(self.fast_outliers, -1)
        self.fast_outliers[-1] = np.minimum(max_fast, self.fast_motion_threshold)
        if self.fast_motion_outlier:
            # Detect fast motion using outlier, based on lower boundary and upper boundary
            Quar1 = np.percentile(self.fast_outliers, self.percentage_quar1)
            Quar3 = np.percentile(self.fast_outliers, self.percentage_quar3)
            InterQuar = (
                self.InterQuar_no_human
                if Quar3 - Quar1 >= self.InterQuar_no_human
                else Quar3 - Quar1
            )
            Lower_boundary = Quar1 - self.Qfactor * InterQuar
            Upper_boundary = Quar3 + self.Qfactor * InterQuar
            self.fast_outlier_detected = max_fast <= Lower_boundary or max_fast >= Upper_boundary
        else:
            self.fast_outlier_detected = False
        fast_motion_detected = self.fast_outlier_detected or max_fast > self.fast_motion_threshold
        fast_presence_distance_index = int(np.argmax(fast_motion))
        fast_presence_distance = self.depths[fast_presence_distance_index]

        # Slow Motion Detector
        slow_motion_detected = any(slow_motion > self.threshold_array)
        slow_presence_distance_index = int(np.argmax(slow_motion - self.threshold_array))
        slow_presence_distance = self.depths[slow_presence_distance_index]

        # False Positive False Negative estimation
        self.fls_pos_frame = np.roll(self.fls_pos_frame, -1)
        self.fls_neg_frame = np.roll(self.fls_neg_frame, -1)
        self.fls_pos_frame[-1] = int(not (fast_motion_detected) and slow_motion_detected)
        self.fls_neg_frame[-1] = int(fast_motion_detected and not (slow_motion_detected))
        fls_neg_detected = sum(self.fls_neg_frame) >= len(self.fls_neg_frame)
        fls_pos_detected = (
            sum(self.fls_pos_frame) >= len(self.fls_pos_frame)
            and self.presence_detector.update_index >= self.human_window_end_index
        )

        if fast_motion_detected:
            self.human_window_end_index = (
                self.human_window_s * self.f + self.presence_detector.update_index
            )
            if self.cal_state:
                self.start_cal_index = self.human_window_end_index

            if slow_motion_detected:
                self.fls_pos_frame = np.zeros(len(self.fls_pos_frame))
                self.fls_neg_frame = np.zeros(len(self.fls_neg_frame))

        if fls_neg_detected:
            self.threshold_array = np.ones(self.num_depths) * self.slow_motion_threshold

        if fls_pos_detected:
            if not (self.cal_state):
                self.start_cal_index = self.presence_detector.update_index
            self.cal_state = True

        # Calibration Steps
        if self.presence_detector.update_index == self.end_cal_index:
            self.cal_state = False
            self.fls_pos_frame = np.zeros(len(self.fls_pos_frame))
            self.fls_neg_frame = np.zeros(len(self.fls_neg_frame))
        elif (
            self.presence_detector.update_index > self.start_cal_index
            and self.presence_detector.update_index < self.end_cal_index
        ):
            self.threshold_stored = np.maximum(self.threshold_stored, slow_motion)
        elif self.presence_detector.update_index == self.start_cal_index:
            self.threshold_stored = np.ones(self.num_depths) * self.slow_motion_threshold
        self.end_cal_index = self.start_cal_index + self.cal_window_s * self.f

        # Option to implement the adaptive value threshold
        if self.adaptive_threshold and (self.presence_detector.update_index >= self.end_cal_index):
            self.threshold_array = self.threshold_stored

        if fast_motion_detected:  # Fast motion is prioritized due to the responsiveness
            presence_detected = True
            self.presence_distance_index = fast_presence_distance_index
            self.presence_distance = fast_presence_distance
            self.information = "fast_motion"
        elif slow_motion_detected:
            presence_detected = True
            self.presence_distance_index = slow_presence_distance_index
            self.presence_distance = slow_presence_distance
            self.information = "slow_motion"
        else:
            presence_detected = False
            self.presence_distance = 0
            self.information = "no_motion"

        if (self.end_cal_index - self.presence_detector.update_index) / self.f <= 10 and (
            self.end_cal_index - self.presence_detector.update_index
        ) / self.f > 0:
            self.information = "adapting_threshold"

        # Histories
        self.fast_history = np.roll(self.fast_history, -1)
        self.fast_history[-1] = fast_motion_detected
        self.slow_history = np.roll(self.slow_history, -1)
        self.slow_history[-1] = slow_motion_detected

        out_data = {
            "frame": presence_result["frame"],
            "fast": presence_result["fast"],
            "slow": presence_result["slow"],
            "fast_motion": fast_motion,
            "slow_motion": slow_motion,
            "presence_distance_index": self.presence_distance_index,
            "presence_distance": self.presence_distance,
            "information": self.information,
            "presence_detected": presence_detected,
            "fls_neg_s": sum(self.fls_neg_frame) / self.f,
            "fls_pos_s": sum(self.fls_pos_frame) / self.f,
            "fast_history": self.fast_history,
            "slow_history": self.slow_history,
            "threshold_array": self.threshold_array,
        }

        return out_data
