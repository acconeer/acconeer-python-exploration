# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et

from .constants import HISTORY_LENGTH_S


A_WEEK_MINUTES = 10080.0
SENSITIVITY_MAX = 1.0
MAX_ALLOWED_NOISE = 20
LP_AVERAGE_CONST_MAX = 0.9
LP_AVERAGE_CONST_INIT = 0.7

DOUBLE_PRESS_RATIO = 1.3  # Ratio between lp_constants for the trigger and cool down filters
THRESHOLD_RATIO = 2.0  # Ratio between trigger and cool down thresholds.

# Constants for calculating the number of intervals actually returned
SPARSE_RESOLUTION = 0.06
EPSILON = 0.00001


def get_sensor_config():
    sensor_config = et.a111.SparseServiceConfig()
    sensor_config.range_interval = [0.06, 0.3]
    sensor_config.sweeps_per_frame = 32
    sensor_config.update_rate = 80
    sensor_config.hw_accelerated_average_samples = 32
    sensor_config.sampling_mode = sensor_config.SamplingMode.A
    sensor_config.profile = sensor_config.Profile.PROFILE_2
    sensor_config.gain = 0.0
    sensor_config.maximize_signal_attenuation = False
    sensor_config.downsampling_factor = 1
    sensor_config.tx_disable = False
    sensor_config.power_save_mode = sensor_config.PowerSaveMode.SLEEP
    sensor_config.repetition_mode = sensor_config.RepetitionMode.HOST_DRIVEN
    return sensor_config


class ProcessingConfiguration(et.configbase.ProcessingConfig):

    recalibration_period = et.configbase.FloatParameter(
        label="Time between recalibrations",
        default_value=10000.0,
        limits=(0.1, A_WEEK_MINUTES),
        unit="min",
        logscale=True,
        updateable=True,
        order=10,
        help="How often the algorithm recalibrates itself",
    )

    sensitivity = et.configbase.FloatParameter(
        label="Detection sensitivity",
        default_value=0.7,
        limits=(0.0, SENSITIVITY_MAX),
        logscale=False,
        updateable=True,
        order=20,
        help="Sensitivity for how easily we detect a button press. "
        "Increasing the value increases the risk of false detects.",
    )

    double_press_speed = et.configbase.FloatParameter(
        label="Double press sensitivity",
        default_value=0.9,
        limits=(0.4, 0.99),
        logscale=False,
        updateable=True,
        order=30,
        help="Sensitivity for double presses. Lower value means more likely to double press."
        "High value in combination with low sensitivity can also cause 'double press' behaviour.",
    )

    def sparse_round_down(self, num):
        """
        Downwards rounding to nearest multiple of 0.06 (sparse resolution in cm)
        """
        return SPARSE_RESOLUTION * round((num - EPSILON) / SPARSE_RESOLUTION)

    def sparse_round_up(self, num):
        """
        Upwards rounding to nearest multiple of 0.06 (sparse resolution in cm)
        """
        return SPARSE_RESOLUTION * round((num + EPSILON) / SPARSE_RESOLUTION)

    def check_sensor_config(self, sensor_config):

        alerts = {
            "processing": [],
            "sensor": [],
        }

        if self.sparse_round_down(sensor_config.range_interval[0]) == 0.0:
            alerts["sensor"].append(
                et.configbase.Warning(
                    "range_interval",
                    "0.0 m point in range, increase range start for better performance",
                )
            )

        if self.recalibration_period == A_WEEK_MINUTES:
            alerts["processing"].append(
                et.configbase.Info("recalibration_period", "Recalibration Off")
            )

        return alerts


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):

        pc = ProcessingConfiguration()
        (rounded_bottom, rounded_top) = (
            pc.sparse_round_down(sensor_config.range_interval[0]),
            pc.sparse_round_up(sensor_config.range_interval[1]),
        )
        num_depths = int(round((rounded_top - rounded_bottom) / SPARSE_RESOLUTION)) + 1

        self.num_depths = num_depths
        self.f = sensor_config.update_rate
        self.signal_history = np.zeros((int(round(self.f * HISTORY_LENGTH_S)), num_depths + 1))
        self.average_history = np.zeros((int(round(self.f * HISTORY_LENGTH_S)), num_depths + 1))
        self.trig_history = np.zeros((int(round(self.f * HISTORY_LENGTH_S)), num_depths + 1))
        self.cool_down_history = np.zeros((int(round(self.f * HISTORY_LENGTH_S)), num_depths + 1))

        self.detection_history = []
        self.frame_count = 0
        self.sweeps_per_frame = sensor_config.sweeps_per_frame

        self.calibration_limit = max(
            1, int(round(sensor_config.update_rate))
        )  # So we always wait one second. This could be more sophisticated.
        self.noise_level_target = MAX_ALLOWED_NOISE

        self.calibrated = 0  # Repeated sending of calibrated signal to exptool plot thread

        self.chilled = [True] * num_depths
        self.initialized = [False] * num_depths

        # Low pass trig
        self.lp_trig = [0.0] * num_depths
        self.lp_trig_const = [0.0] * num_depths

        # Low pass cool down
        self.lp_cool_down = [0.0] * num_depths
        self.lp_cool_down_const = [0.0] * num_depths

        # Low pass average
        self.lp_average_const = [LP_AVERAGE_CONST_INIT] * num_depths

        self.lp_average = [0.0] * num_depths

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.sensitivity = processing_config.sensitivity
        self.double_press_speed = processing_config.double_press_speed
        if processing_config.recalibration_period == A_WEEK_MINUTES:
            self.recalibration_frame_period = -1  # Effectively turning it off
        else:
            self.recalibration_frame_period = int(
                round(processing_config.recalibration_period * 60 * self.f)
            )

        self.set_sensitivity()
        self.set_double_press_speed()

    def set_double_press_speed(self):
        for i in range(self.num_depths):
            self.lp_trig_const[i] = self.double_press_speed / DOUBLE_PRESS_RATIO
            self.lp_cool_down_const[i] = self.double_press_speed

    def set_sensitivity(self):
        """
        Function to map the idea of "sensitivity between 0-1" to an actual threshold.
        """
        inv_sensitivity = (
            (SENSITIVITY_MAX - self.sensitivity)
        ) * 10.0  # since intuitively high sensitivity -> more likely to detect
        sens = 2 ** (1.1 * inv_sensitivity) * 600  # Yielding a nice exponential curve between 0-10
        self.threshold_trig = int(sens)
        self.threshold_cool_down = int(self.threshold_trig / THRESHOLD_RATIO)

    def lp_cool_down_filter(self, data, index):
        ret = int(
            self.lp_cool_down_const[index] * self.lp_cool_down[index]
            + (1.0 - self.lp_cool_down_const[index]) * data
        )
        self.lp_cool_down[index] = ret
        return ret

    def lp_trig_filter(self, data, index):
        ret = int(
            self.lp_trig_const[index] * self.lp_trig[index]
            + (1.0 - self.lp_trig_const[index]) * data
        )
        self.lp_trig[index] = ret
        return ret

    def lp_average_filter(self, data, index):
        ret = int(
            self.lp_average_const[index] * self.lp_average[index]
            + (1.0 - self.lp_average_const[index]) * data
        )
        self.lp_average[index] = ret
        return ret

    def calibrate(self, index):
        # Update the lp_average constant based on the noise levels.
        max_diff = max(
            abs(
                self.average_history[-self.calibration_limit :, index]
                - self.signal_history[-self.calibration_limit :, index]
            )
        )

        lp_new = (self.lp_average_const[index] * self.noise_level_target) / max_diff
        if lp_new < LP_AVERAGE_CONST_MAX:
            self.lp_average_const[index] = lp_new

    def detect(self, trig_val, cool_down_val, index):
        trig = False

        if trig_val > self.threshold_trig:
            if all(self.chilled):
                trig = True
            self.chilled[index] = False
        if cool_down_val < self.threshold_cool_down:
            self.chilled[index] = True

        return trig

    def process(self, frame, data_info):

        detections = [False] * self.num_depths
        signal = [0.0] * self.num_depths

        for i in range(frame.shape[1]):

            if not self.initialized[i]:
                self.lp_average[i] = int(np.mean(frame[:, i], axis=0))
                self.initialized[i] = True

            signal[i] = np.mean(frame[:, i], axis=0)
            self.signal_history[-1, -1] = max(self.signal_history[-1, :-1])

            lp_average = self.lp_average_filter(signal[i], i)  # Low pass to smooth the signal
            self.average_history[-1, -1] = max(self.average_history[-1, :-1])

            diff = int(abs(lp_average - signal[i]))

            if diff < self.noise_level_target:
                diff = 0  # Get back to "detect" state asap

            diff_sq = (
                diff * diff
            )  # Squaring yields a bit simpler behaviour with regards to thresholds.

            trig_val = self.lp_trig_filter(diff_sq, i)
            cool_down_val = self.lp_cool_down_filter(diff_sq, i)

            # Triggering checks if it is considered a button press.
            # Cool down checks if we can trigger again.
            detection = self.detect(trig_val, cool_down_val, i)

            if self.frame_count % self.recalibration_frame_period == self.calibration_limit:
                self.calibrate(i)
                self.calibrated = 5

            if self.frame_count <= self.calibration_limit:
                detection = False

            self.signal_history[-1, i] = signal[i]

            self.average_history[-1, i] = lp_average

            self.trig_history[-1, i] = trig_val

            self.cool_down_history[-1, i] = cool_down_val

            detections[i] = detection

        detection = any(detections)
        self.cool_down_history[-1, -1] = max(self.cool_down_history[-1, :-1])

        self.trig_history[-1, -1] = max(self.trig_history[-1, :-1])

        self.cool_down_history = np.roll(self.cool_down_history, -1, axis=0)
        self.trig_history = np.roll(self.trig_history, -1, axis=0)
        self.average_history = np.roll(self.average_history, -1, axis=0)
        self.signal_history = np.roll(self.signal_history, -1, axis=0)

        if detection:
            self.detection_history.append(self.frame_count)

        if self.calibrated > 0:
            calibrated = True
            self.calibrated -= 1
        else:
            calibrated = False

        out_data = {
            "signal_history": self.signal_history[:, -1],
            "average_history": self.average_history[:, -1],
            "trig_history": self.trig_history[:, -1],
            "cool_down_history": self.cool_down_history[:, -1],
            "threshold": self.threshold_trig,
            "detection_history": (np.array(self.detection_history) - self.frame_count) / self.f,
            "detection": detection,
            "signal": signal,
            "calibrated": calibrated,
        }

        self.frame_count += 1

        return out_data
