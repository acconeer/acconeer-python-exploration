# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_3
    config.range_interval = [0.48, 0.72]
    config.sweeps_per_frame = 16
    config.hw_accelerated_average_samples = 60
    config.update_rate = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1
    WINDOW_SIZE_POW_OF_2_MAX = 12
    ROLLING_HISTORY_SIZE_MAX = 1000

    show_time_domain = et.configbase.BoolParameter(
        label="Show data in time domain",
        default_value=True,
        updateable=True,
        order=0,
    )

    show_spect_history = et.configbase.BoolParameter(
        label="Show spectrum history",
        default_value=False,
        updateable=True,
        order=10,
    )

    show_depthwise_spect = et.configbase.BoolParameter(
        label="Show depthwise spectrum",
        default_value=False,
        updateable=True,
        order=20,
    )

    window_size_pow_of_2 = et.configbase.FloatParameter(
        label="Window size, power of 2",
        default_value=8,
        limits=(3, WINDOW_SIZE_POW_OF_2_MAX),
        decimals=0,
        updateable=True,
        order=100,
    )

    _window_size = et.configbase.get_virtual_parameter_class(et.configbase.IntParameter)(
        label="Window size",
        get_fun=lambda conf: 2 ** int(conf.window_size_pow_of_2),
        visible=False,
    )

    overlap = et.configbase.FloatParameter(
        label="Overlap",
        default_value=0.95,
        limits=(0, 1),
        updateable=True,
        order=200,
    )

    rolling_history_size = et.configbase.FloatParameter(
        label="Rolling history size",
        default_value=100,
        decimals=0,
        logscale=True,
        limits=(10, ROLLING_HISTORY_SIZE_MAX),
        updateable=True,
        order=300,
    )

    def check(self):
        alerts = super().check()

        msg = "{}".format(self._window_size)
        alerts.append(et.configbase.Info("window_size_pow_of_2", msg))

        return alerts


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.f = sensor_config.update_rate
        depths = et.a111.get_range_depths(sensor_config, session_info)
        self.num_depths = depths.size

        max_window_size = 2**ProcessingConfiguration.WINDOW_SIZE_POW_OF_2_MAX
        self.sweep_history = np.full([max_window_size, self.num_depths], np.nan)

        self.collapsed_asd = None
        self.collapsed_asd_history = None

        self.window_size = None
        self.frames_between_updates = None
        self.rolling_history_size = None

        self.tick_idx = 0
        self.last_update_tick = 0

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        invalid = self.window_size != processing_config._window_size

        self.window_size = processing_config._window_size
        self.frames_between_updates = int(
            round(self.window_size * (1 - processing_config.overlap))
        )

        self.rolling_history_size = int(processing_config.rolling_history_size)

        if invalid:
            self.collapsed_asd_history = np.zeros(
                [
                    ProcessingConfiguration.ROLLING_HISTORY_SIZE_MAX,
                    self.window_size // 2,
                ]
            )

        if invalid and self.tick_idx > 0:
            self.update_spect()

    def process(self, data, data_info):
        frame = data

        mean_sweep = frame.mean(axis=0)

        self.sweep_history = np.roll(self.sweep_history, -1, axis=0)
        self.sweep_history[-1] = mean_sweep

        outdated = (self.tick_idx - self.last_update_tick) > self.frames_between_updates
        if self.tick_idx == 0 or outdated:
            self.update_spect()

        self.tick_idx += 1

        return self.gather_result()

    def update_spect(self):
        x = self.sweep_history[-self.window_size :]
        x = x - np.nanmean(x, axis=0, keepdims=True)
        x = np.nan_to_num(x)
        fft = np.fft.rfft(x.T * np.hanning(x.shape[0]), axis=1)
        asd = np.abs(fft)[:, 1:]

        self.collapsed_asd = asd.sum(axis=0)
        self.dw_asd = asd

        self.collapsed_asd_history = np.roll(self.collapsed_asd_history, -1, axis=0)
        self.collapsed_asd_history[-1] = self.collapsed_asd

        self.last_update_tick = self.tick_idx

    def gather_result(self):
        ts = np.arange(-self.window_size, 0, dtype="float") + 1
        fs = np.arange(self.window_size // 2, dtype="float") + 1

        if self.f:
            ts *= 1 / self.f
            fs *= 0.5 * self.f / fs[-1]

        cropped_history = self.collapsed_asd_history[-self.rolling_history_size :]

        return {
            "ts": ts,
            "sweep_history": self.sweep_history[-self.window_size :],
            "fs": fs,
            "collapsed_asd": self.collapsed_asd,
            "collapsed_asd_history": cropped_history,
            "dw_asd": self.dw_asd,
        }
