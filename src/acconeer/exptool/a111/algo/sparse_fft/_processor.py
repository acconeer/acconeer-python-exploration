# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_3
    config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.A
    config.range_interval = [0.24, 0.48]
    config.sweeps_per_frame = 64
    config.sweep_rate = 3e3
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    show_data_plot = et.configbase.BoolParameter(
        label="Show data",
        default_value=True,
        updateable=True,
        order=0,
    )

    show_speed_plot = et.configbase.BoolParameter(
        label="Show speed on FFT y-axis",
        default_value=False,
        updateable=True,
        order=10,
    )


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        pass

    def process(self, data, data_info):
        frame = data

        zero_mean_frame = frame - frame.mean(axis=0, keepdims=True)
        fft = np.fft.rfft(zero_mean_frame.T * np.hanning(frame.shape[0]), axis=1)
        abs_fft = np.abs(fft)

        return {
            "frame": frame,
            "abs_fft": abs_fft,
        }
