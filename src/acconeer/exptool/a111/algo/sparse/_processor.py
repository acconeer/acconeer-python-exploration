# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et
from acconeer.exptool.a111.algo.presence_detection_sparse import _processor as presence_processing


def get_sensor_config():
    sensor_config = et.a111.SparseServiceConfig()
    sensor_config.range_interval = [0.24, 1.20]
    sensor_config.update_rate = 60
    sensor_config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.A
    sensor_config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_3
    sensor_config.hw_accelerated_average_samples = 60
    return sensor_config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 2

    history_length = et.configbase.IntParameter(
        label="History length",
        default_value=100,
    )

    show_data_history_plot = et.configbase.BoolParameter(
        label="Show data history",
        default_value=True,
        updateable=True,
        order=110,
    )

    show_move_history_plot = et.configbase.BoolParameter(
        label="Show movement history",
        default_value=True,
        updateable=True,
        order=120,
    )


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        num_sensors = len(sensor_config.sensor)
        num_depths = et.a111.get_range_depths(sensor_config, session_info).size
        history_len = processing_config.history_length

        pd_config = presence_processing.ProcessingConfiguration()
        processor_class = presence_processing.Processor

        try:
            self.pd_processors = []
            for _ in sensor_config.sensor:
                p = processor_class(sensor_config, pd_config, session_info)
                self.pd_processors.append(p)
        except AssertionError:
            self.pd_processors = None

        self.data_history = np.ones([history_len, num_sensors, num_depths]) * 2**15
        self.presence_history = np.zeros([history_len, num_sensors, num_depths])

    def process(self, data, data_info):
        if self.pd_processors:
            if data_info is None:
                processed_datas = [p.process(s, None) for s, p in zip(data, self.pd_processors)]
            else:
                processed_datas = [
                    p.process(s, i) for s, i, p in zip(data, data_info, self.pd_processors)
                ]

            presences = [d["depthwise_presence"] for d in processed_datas]

            self.presence_history = np.roll(self.presence_history, -1, axis=0)
            self.presence_history[-1] = presences

        self.data_history = np.roll(self.data_history, -1, axis=0)
        self.data_history[-1] = data.mean(axis=1)

        out_data = {
            "data": data,
            "data_history": self.data_history,
            "presence_history": self.presence_history,
        }

        return out_data
