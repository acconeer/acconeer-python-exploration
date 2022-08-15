# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et

from .constants import HISTORY_LENGTH_S


def get_sensor_config():
    config = et.a111.EnvelopeServiceConfig()
    config.profile = et.a111.EnvelopeServiceConfig.Profile.PROFILE_1
    config.range_interval = [0.04, 0.05]
    config.running_average_factor = 0.01
    config.maximize_signal_attenuation = True
    config.update_rate = 60
    config.gain = 0.2
    config.repetition_mode = et.a111.EnvelopeServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 2

    signal_tc_s = et.configbase.FloatParameter(
        label="Signal time constant",
        unit="s",
        default_value=5.0,
        limits=(0.01, 10),
        logscale=True,
        updateable=True,
        order=20,
        help="Time constant of the low pass filter for the signal.",
    )

    rel_dev_tc_s = et.configbase.FloatParameter(
        label="Relative deviation time constant",
        unit="s",
        default_value=0.2,
        limits=(0.01, 2),
        logscale=True,
        updateable=True,
        order=30,
        help="Time constant of the low pass filter for the relative deviation.",
    )

    threshold = et.configbase.FloatParameter(
        label="Detection threshold",
        default_value=0.2,
        decimals=3,
        limits=(0.001, 0.5),
        updateable=True,
        logscale=True,
        order=10,
        help='Level at which the detector output is considered as a "button press". '
        "Note that this might need adjustment depending "
        "on different board models in order to detect movement.",
    )

    buttonpress_length_s = et.configbase.FloatParameter(
        label="Button press length",
        unit="s",
        default_value=2.0,
        limits=(0.01, 5),
        logscale=False,
        updateable=True,
        order=40,
        help="The time after a detected button press when no further detection should occur.",
    )

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }

        alerts["processing"].append(
            et.configbase.Info(
                "threshold", "Threshold level should be adjusted \ndepending on board model."
            )
        )

        return alerts


class Processor:
    # lp(f): low pass (filtered)
    # cut: cutoff frequency [Hz]
    # tc: time constant [s]
    # sf: smoothing factor [dimensionless]

    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate

        self.signal_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.signal_lp_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.rel_dev_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.rel_dev_lp_history = np.zeros(int(round(self.f * HISTORY_LENGTH_S)))
        self.detection_history = []
        self.signal_lp = 0.0
        self.rel_dev_lp = 0
        self.sweep_index = 0
        self.last_detection_sweep = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.threshold = processing_config.threshold

        self.sf_signal = np.exp(-1.0 / (processing_config.signal_tc_s * self.f))
        self.sf_rel_dev = np.exp(-1.0 / (processing_config.rel_dev_tc_s * self.f))
        self.buttonpress_length_sweeps = processing_config.buttonpress_length_s * self.f

    def process(self, data, data_info):
        sweep = data

        # Sum the full sweep to a single number
        signal = np.mean(sweep)

        # Exponential filtering of the signal
        sf = min(self.sf_signal, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.signal_lp = sf * self.signal_lp + (1.0 - sf) * signal

        # The relative difference
        rel_dev = np.square((signal - self.signal_lp) / self.signal_lp)

        # Exponential filtering of the difference
        sf = min(self.sf_rel_dev, 1.0 - 1.0 / (1.0 + self.sweep_index))
        self.rel_dev_lp = sf * self.rel_dev_lp + (1.0 - sf) * rel_dev

        # Check detection
        detection = False
        sweeps_since_last_detect = self.sweep_index - self.last_detection_sweep
        detection_long_enough_ago = sweeps_since_last_detect > self.buttonpress_length_sweeps
        over_threshold = self.rel_dev_lp > self.threshold
        if over_threshold and detection_long_enough_ago:
            self.last_detection_sweep = self.sweep_index
            detection = True

        # Save all signal in history arrays.
        self.signal_history = np.roll(self.signal_history, -1)
        self.signal_history[-1] = signal

        self.signal_lp_history = np.roll(self.signal_lp_history, -1)
        self.signal_lp_history[-1] = self.signal_lp

        self.rel_dev_history = np.roll(self.rel_dev_history, -1)
        self.rel_dev_history[-1] = rel_dev

        self.rel_dev_lp_history = np.roll(self.rel_dev_lp_history, -1)
        self.rel_dev_lp_history[-1] = self.rel_dev_lp

        if detection:
            self.detection_history.append(self.sweep_index)

        while (
            len(self.detection_history) > 0
            and self.sweep_index - self.detection_history[0] > HISTORY_LENGTH_S * self.f
        ):
            self.detection_history.remove(self.detection_history[0])

        out_data = {
            "signal_history": self.signal_history,
            "signal_lp_history": self.signal_lp_history,
            "rel_dev_history": self.rel_dev_history,
            "rel_dev_lp_history": self.rel_dev_lp_history,
            "detection_history": (np.array(self.detection_history) - self.sweep_index) / self.f,
            "detection": detection,
            "sweep_index": self.sweep_index,
            "threshold": self.threshold,
        }

        self.sweep_index += 1

        return out_data
