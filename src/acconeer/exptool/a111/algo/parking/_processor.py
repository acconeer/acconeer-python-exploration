# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et


ENVELOPE_BACKGROUND_LEVEL = 100


def get_sensor_config():
    config = et.a111.EnvelopeServiceConfig()
    config.downsampling_factor = 2
    config.range_interval = [0.12, 0.62]
    config.running_average_factor = 0
    config.update_rate = 0.5
    config.hw_accelerated_average_samples = 20
    config.power_save_mode = et.a111.EnvelopeServiceConfig.PowerSaveMode.OFF
    config.asynchronous_measurement = False

    return config


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.session_info = session_info

        self.f = sensor_config.update_rate
        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        self.norm_depths = self.depths / self.depths[-1]  # normalize by max value

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):

        start = self.session_info["range_start_m"]
        step = self.session_info["step_length_m"]

        # Test if we should deal with direct leakage
        if start > processing_config.depth_leak_end:
            self.depth_leak_sample = 0
            self.depth_leak_end = 0
        else:
            self.depth_leak_sample = processing_config.depth_leak_sample
            self.depth_leak_end = processing_config.depth_leak_end

        self.detector_queue_target_length = processing_config.detector_queue_target_length
        self.weight_threshold = processing_config.weight_threshold
        self.weight_ratio_limit = processing_config.weight_ratio_limit
        self.distance_difference_limit = processing_config.distance_difference_limit

        self.leak_sample_index = int(round((self.depth_leak_sample - start) / step))
        self.leak_end_index = int(round((self.depth_leak_end - start) / step))
        self.leak_estimate_depths = np.array(
            [
                self.depths[0] + step * self.leak_sample_index,
                self.depths[0] + step * self.leak_end_index,
            ]
        )
        self.queued_weights = []
        self.queued_distances = []

        history_length = int(round(self.f * processing_config.history_length_s)) + 1
        self.detection_history = np.zeros(history_length) * float("nan")
        self.detection_history_t = np.linspace(-(history_length - 1) / self.f, 0, history_length)

    def process(self, data, data_info):
        sweep = data

        valid_leak_setup = (
            0 <= self.leak_sample_index
            and self.leak_sample_index < self.leak_end_index
            and self.leak_sample_index < len(sweep)
        )
        if valid_leak_setup:
            leak_amplitude = sweep[self.leak_sample_index]
            a_leak = max(leak_amplitude - ENVELOPE_BACKGROUND_LEVEL, 0)
            leak_step = a_leak / (self.leak_end_index - self.leak_sample_index)
            leak_start = self.leak_end_index * leak_step + ENVELOPE_BACKGROUND_LEVEL

            bg_near = np.linspace(leak_start, ENVELOPE_BACKGROUND_LEVEL, self.leak_end_index + 1)
            bg_far_len = len(sweep) - (self.leak_end_index + 1)
            if bg_far_len > 0:
                bg_far = np.ones(bg_far_len) * ENVELOPE_BACKGROUND_LEVEL
                background = np.append(bg_near, bg_far)
            else:
                background = bg_near[: len(sweep)]
        else:
            leak_amplitude = float("nan")
            background = np.ones(len(sweep)) * ENVELOPE_BACKGROUND_LEVEL

        leak_estimate = np.array([leak_amplitude, ENVELOPE_BACKGROUND_LEVEL])
        samples_above_bg = np.fmax(sweep - background, 0)
        weight = (
            np.fmin(samples_above_bg / ENVELOPE_BACKGROUND_LEVEL, 1)
            * samples_above_bg
            * self.norm_depths
        )

        weight_sum = np.sum(weight)

        sweep_weight = weight_sum / len(weight)
        sweep_distance = np.sum(weight * self.depths) / weight_sum

        # Pops the oldest item in the detector queue if the queue is full
        if len(self.queued_weights) == self.detector_queue_target_length:
            self.queued_weights = self.queued_weights[1:]
            self.queued_distances = self.queued_distances[1:]

        self.queued_weights.append(sweep_weight)
        self.queued_distances.append(sweep_distance)

        weight_min = min(self.queued_weights)
        weight_max = max(self.queued_weights)
        distance_min = min(self.queued_distances)
        distance_max = max(self.queued_distances)

        # The final criterion evaluation for parking detection
        detection = (
            len(self.queued_weights) == self.detector_queue_target_length
            and weight_min >= self.weight_threshold
            and weight_max / weight_min <= self.weight_ratio_limit
            and distance_max - distance_min <= self.distance_difference_limit
        )

        self.detection_history = np.roll(self.detection_history, -1)
        self.detection_history[-1] = detection

        # Calculates limits_center used to visualize the detection criterion
        limits_center = (np.sqrt(weight_min * weight_max), (distance_min + distance_max) / 2)

        out_data = {
            "sweep": sweep,
            "leak_estimate": leak_estimate,
            "leak_estimate_depths": self.leak_estimate_depths,
            "background": background,
            "weight": weight,
            "queued_weights": np.array(self.queued_weights),
            "queued_distances": np.array(self.queued_distances),
            "limits_center": limits_center,
            "detection_history": self.detection_history,
            "detection_history_t": self.detection_history_t,
        }

        return out_data


class ProcessingConfiguration(et.configbase.ProcessingConfig):

    VERSION = 3

    depth_leak_sample = et.configbase.FloatParameter(
        label="Leak sample position",
        default_value=0.15,
        limits=(0.05, 0.25),
        unit="m",
        logscale=False,
        decimals=3,
        updateable=True,
        order=0,
        help="Distance from the sensor for the leak sample position",
    )

    depth_leak_end = et.configbase.FloatParameter(
        label="Leak end position",
        default_value=0.30,
        limits=(0.10, 0.50),
        unit="m",
        logscale=False,
        decimals=3,
        updateable=True,
        order=1,
        help="Worst case distance from the sensor for the end of leak reflections",
    )

    detector_queue_target_length = et.configbase.IntParameter(
        label="Detector queue length",
        default_value=3,
        limits=(1, 10),
        updateable=True,
        order=3,
        help=(
            "Car detection criterion parameter: "
            "The number of sweep value pairs (weight, distance) in the detector queue"
        ),
    )

    weight_threshold = et.configbase.FloatParameter(
        label="Weight threshold",
        default_value=5,
        limits=(0.5, 500),
        logscale=True,
        decimals=1,
        updateable=True,
        order=4,
        help=(
            "Car detection criterion parameter: "
            "Minimal value of the weights in the detector queue"
        ),
    )

    weight_ratio_limit = et.configbase.FloatParameter(
        label="Weight ratio limit",
        default_value=3,
        limits=(1, 10),
        logscale=True,
        decimals=2,
        updateable=True,
        order=5,
        help=(
            "Car detection criterion parameter: "
            "Maximal ratio between the maximal and the minimal weights in the detector queue"
        ),
    )

    distance_difference_limit = et.configbase.FloatParameter(
        label="Distance limit",
        default_value=0.2,
        limits=(0.01, 0.5),
        logscale=True,
        decimals=3,
        updateable=True,
        order=6,
        help=(
            "Car detection criterion parameter: "
            "Maximal difference between the maximal and minimal distances in the detector queue"
        ),
    )

    history_length_s = et.configbase.FloatParameter(
        label="History length",
        unit="s",
        default_value=300,
        limits=(1, 3600),
        logscale=True,
        decimals=0,
        updateable=True,
        order=100,
        help='The time interval that is shown in the "Detection history" plot',
    )

    def check(self):
        alerts = []

        if self.depth_leak_sample >= self.depth_leak_end:
            alerts.append(
                et.configbase.Error("depth_leak_sample", "Must be less than the leak end position")
            )

        return alerts

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }
        if sensor_config.update_rate is None:
            alerts["sensor"].append(et.configbase.Error("update_rate", "Must be set"))

        if not sensor_config.noise_level_normalization:
            alerts["sensor"].append(
                et.configbase.Error("noise_level_normalization", "Must be set")
            )

        return alerts
