# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et
from acconeer.exptool.a111.algo import presence_detection_sparse


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_2
    config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.B
    config.range_interval = [0.12, 0.3]
    config.update_rate = 80
    config.sweeps_per_frame = 32
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):

    detection_threshold = et.configbase.FloatParameter(
        label="Detection threshold",
        default_value=1.4,
        limits=(1.1, 10.0),
        updateable=True,
        order=0,
        help="Level at which to trigger a button press.",
    )

    cool_down_threshold = et.configbase.FloatParameter(
        label="Cool down threshold",
        default_value=1.1,
        limits=(1.0, 5.0),
        updateable=True,
        order=1,
        help="Level at which to be able to trigger again.",
    )

    cool_down_time = et.configbase.FloatParameter(
        label="Cool down time",
        default_value=0,
        limits=(0, 1000),
        updateable=True,
        order=2,
        unit="ms",
        help="Minimal time between triggers.",
    )

    history_length_s = et.configbase.FloatParameter(
        label="Length of display history",
        default_value=10,
        limits=(0, 20),
        updateable=False,
        order=3,
        unit="s",
        help="How long back the display history shows.",
    )

    history_plot_ceiling = et.configbase.FloatParameter(
        label="Ceiling for the trigger value plot",
        default_value=5.0,
        limits=(0, 10.0),
        updateable=True,
        order=1,
        help="Max level for the trigger value plot.",
    )

    def check_sensor_config(self, conf):
        alerts = {
            "processing": [],
            "sensor": [],
        }
        if conf.range_interval[0] < 0.12:
            alerts["sensor"].append(
                et.configbase.Error(
                    "range_interval",
                    "Must be above 0.12. For closer range use Button Press instead.",
                )
            )

        return alerts


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):

        # Config of the presence detector
        presence_config = presence_detection_sparse.ProcessingConfiguration()
        presence_config.detection_threshold = processing_config.detection_threshold
        presence_config.intra_frame_weight = 1.0
        presence_config.intra_frame_time_const = 0.05
        presence_config.output_time_const = 0.02

        self.presence_detector = presence_detection_sparse.Processor(
            sensor_config, presence_config, session_info
        )
        self.processing_config = processing_config
        self.update_rate = sensor_config.update_rate

        history_length = int(processing_config.history_length_s * sensor_config.update_rate)
        self.detection_history = np.zeros(history_length)

        self.cool_trig = True
        self.cool_time = True
        self.cool_counter = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.cool_down_n_tics = int(processing_config.cool_down_time * self.update_rate / 1000.0)
        self.cool_down_threshold = processing_config.cool_down_threshold
        self.detection_threshold = processing_config.detection_threshold

    def process(self, data, data_info):
        presence_result = self.presence_detector.process(data, data_info)

        score = presence_result["presence_score"]
        button_press = False

        if presence_result["presence_detected"] and self.cool_trig and self.cool_time:
            button_press = True
            self.cool_trig = False
            self.cool_time = False

        if not self.cool_trig and score < self.cool_down_threshold:
            self.cool_trig = True
            self.cool_counter = self.cool_down_n_tics

        if not self.cool_time and self.cool_trig:
            if self.cool_counter > 0:
                self.cool_counter -= 1
            if self.cool_counter == 0:
                self.cool_time = True

        presence_result["detection"] = button_press
        self.detection_history = np.roll(self.detection_history, -1)
        self.detection_history[-1] = button_press
        presence_result["detection_history"] = self.detection_history

        return presence_result
