# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from enum import Enum

import numpy as np

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.EnvelopeServiceConfig()
    config.range_interval = [0.2, 0.8]
    config.hw_accelerated_average_samples = 15
    config.update_rate = 30
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    class BackgroundMode(Enum):
        SUBTRACT = "Subtract"
        LIMIT = "Limit"

    show_peak_depths = et.configbase.BoolParameter(
        label="Show peak distances",
        default_value=True,
        updateable=True,
        order=-10,
    )

    bg_buffer_length = et.configbase.IntParameter(
        default_value=50,
        limits=(1, 200),
        label="Background buffer length",
        order=0,
    )

    bg_mode = et.configbase.EnumParameter(
        label="Background mode",
        default_value=BackgroundMode.SUBTRACT,
        enum=BackgroundMode,
        updateable=True,
        order=20,
    )

    history_length = et.configbase.IntParameter(
        default_value=100,
        limits=(10, 1000),
        label="History length",
        order=30,
    )


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self._session_info = session_info

        self.processing_config = processing_config

        self.depths = et.a111.get_range_depths(sensor_config, session_info)
        num_depths = self.depths.size
        num_sensors = len(sensor_config.sensor)

        buffer_length = self.processing_config.bg_buffer_length
        self.bg_buffer = np.zeros([buffer_length, num_sensors, num_depths])

        history_length = self.processing_config.history_length
        self.history = np.zeros([history_length, num_sensors, num_depths])

        self.data_index = 0

    def process(self, data, data_info):
        bg = None
        output_data = data

        self.history = np.roll(self.history, -1, axis=0)
        self.history[-1] = output_data

        peak_ampls = [np.max(sweep) for sweep in output_data]
        peak_depths = [self.depths[np.argmax(sweep)] for sweep in output_data]
        filtered_peak_depths = [d if a > 200 else None for d, a in zip(peak_depths, peak_ampls)]

        output = {
            "output_data": output_data,
            "bg": bg,
            "history": self.history,
            "peak_depths": filtered_peak_depths,
        }

        self.data_index += 1

        return output
