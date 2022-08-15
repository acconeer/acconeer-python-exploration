# Copyright (c) Acconeer AB, 2022
# All rights reserved

import logging
from time import sleep, time

import numpy as np

from acconeer.exptool.a111 import SDK_VERSION
from acconeer.exptool.a111._clients.base import BaseClient, ClientError, decode_version_str
from acconeer.exptool.a111._configs import BaseServiceConfig
from acconeer.exptool.a111._modes import Mode


log = logging.getLogger(__name__)


START_KEY = "range_start_m"
LENGTH_KEY = "range_length_m"
STEP_LENGTH_KEY = "step_length_m"
MISSED_GET_NEXT_KEY = "missed_data"
DATA_SATURATED_KEY = "data_saturated"
DATA_QUALITY_WARNING_KEY = "data_quality_warning"
DATA_LENGTH_KEY = "data_length"


class MockClient(BaseClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _connect(self):
        info = {}
        info.update(decode_version_str(SDK_VERSION))
        info["mock"] = True
        return info

    def _setup_session(self, config):
        self._config = config

        update_rate_limit = 100

        if config.mode == Mode.SPARSE:
            if config.sweep_rate is not None:
                sparse_frame_rate_limit = config.sweep_rate / config.sweeps_per_frame
                update_rate_limit = min(update_rate_limit, sparse_frame_rate_limit)

        if config.update_rate is None:
            self._update_rate = update_rate_limit
            self._missed = False
        else:
            self._update_rate = min(config.update_rate, update_rate_limit)
            self._missed = config.update_rate > self._update_rate

        try:
            mock_class = MOCK_CLASS_MAP[config.mode]
        except KeyError as e:
            raise ClientError("mode not supported") from e

        self._mocker = mock_class(config)
        info = self._mocker.session_info
        info["stitch_count"] = 0
        return info

    def _start_session(self):
        self._start_time = time()
        self._data_count = 0

    def _get_next(self):
        config = self._config

        self._data_count += 1

        data_capture_time = self._data_count / self._update_rate
        now = time() - self._start_time
        if data_capture_time > now:
            sleep(data_capture_time - now)

        args = (data_capture_time, self._data_count)
        num_sensors = len(config.sensor)

        if self.squeeze and num_sensors == 1:
            info, data = self._mocker.get_next(*args, 0)
            info[MISSED_GET_NEXT_KEY] = self._missed
        else:
            idx_offset = max(0, (num_sensors - 1) / 2)
            out = [self._mocker.get_next(*args, i - idx_offset) for i in range(num_sensors)]
            info, data = zip(*out)
            data = np.array(data)
            info = list(info)

            for d in info:
                d[MISSED_GET_NEXT_KEY] = self._missed

        return info, data

    def _stop_session(self):
        pass

    def _disconnect(self):
        pass

    @property
    def description(self):
        return "simulated interface"


class DenseMocker:
    BASE_STEP_LENGTH = 0.485e-3

    def __init__(self, config):
        self.config = config

        step_length = self.BASE_STEP_LENGTH * config.downsampling_factor

        self.num_depths = int(round(config.range_length / step_length)) + 1

        self.session_info = {
            START_KEY: config.range_start,
            LENGTH_KEY: config.range_length,
            DATA_LENGTH_KEY: self.num_depths,
            STEP_LENGTH_KEY: step_length,
        }

        self.range_center = config.range_start + config.range_length / 2
        self.depths = np.linspace(*config.range_interval, self.num_depths)


class EnvelopeMocker(DenseMocker):
    def get_next(self, t, i, offset):
        info = {
            DATA_SATURATED_KEY: False,
            DATA_QUALITY_WARNING_KEY: False,
        }

        noise = 100 + 20 * np.random.randn(self.num_depths)
        noise = filtfilt_simple(noise, 0.98)

        ampl = 2000 + np.random.randn() * 20
        center = self.range_center
        center += np.random.randn() * 0.2e-3
        center += offset * 0.1
        profile = getattr(self.config, "profile", BaseServiceConfig.Profile.PROFILE_2)
        s = 0.01 + (profile.json_value - 1.0) * 0.03
        signal = ampl * np.exp(-np.square((self.depths - center) / s))

        data = signal + noise

        data = np.rint(data)

        return info, data


class IQMocker(DenseMocker):
    def get_next(self, t, i, offset):
        info = {
            DATA_SATURATED_KEY: False,
            DATA_QUALITY_WARNING_KEY: False,
        }

        noise = np.random.randn(self.num_depths) + 1j * np.random.randn(self.num_depths)
        noise *= 0.015

        ampl = 0.2 * (1 + 0.03 * np.random.randn())
        center = self.range_center
        center += np.random.randn() * (3 / 360) * 2.5e-3
        center += offset * 0.1
        center += 4e-3 * np.sin(t)
        xs = self.depths - center
        signal = ampl * np.exp(2j * np.pi * xs / 2.5e-3) * np.exp(-np.square(xs / 0.05))

        data = signal + noise
        data *= np.exp(-2j * np.pi * self.depths / 2.5e-3)
        data = filtfilt_simple(data, 0.98)

        return info, data


class PowerBinMocker(EnvelopeMocker):
    def __init__(self, config):
        self.config = config

        step_length = self.BASE_STEP_LENGTH * config.downsampling_factor

        self.num_depths = config.bin_count or int(round(config.range_length / 0.1)) + 1

        self.session_info = {
            START_KEY: config.range_start,
            LENGTH_KEY: config.range_length,
            DATA_LENGTH_KEY: self.num_depths,
            STEP_LENGTH_KEY: step_length,
            "bin_count": self.num_depths,
        }

        self.range_center = config.range_start + config.range_length / 2
        self.depths = np.linspace(*config.range_interval, self.num_depths)


class SparseMocker:
    BASE_STEP_LENGTH = 0.06

    def __init__(self, config):
        self.config = config

        step_length = 0.06 * config.downsampling_factor

        start_point = int(round(config.range_start / self.BASE_STEP_LENGTH))
        start = start_point * self.BASE_STEP_LENGTH
        length_point = int(round((config.range_end - start) / step_length))
        self.num_depths = length_point + 1
        end_point = start_point + length_point
        end = end_point * self.BASE_STEP_LENGTH

        self.session_info = {
            START_KEY: start,
            LENGTH_KEY: end - start,
            DATA_LENGTH_KEY: self.num_depths * config.sweeps_per_frame,
            STEP_LENGTH_KEY: step_length,
            "sweep_rate": config.sweep_rate or 5e3,
        }

        self.range_center = (start + end) / 2
        self.depths = np.linspace(start, end, self.num_depths)

    def get_next(self, t, i, offset):
        info = {
            DATA_SATURATED_KEY: False,
        }

        num_sweeps = self.config.sweeps_per_frame

        noise = 100 * np.random.randn(num_sweeps, self.num_depths)

        xs = self.depths - self.range_center + 0.1 * np.sin(t)
        signal = 5000 * np.exp(-np.square(xs / 0.1)) * np.sin(xs / 2.5e-3)

        data = 2**15 + noise + np.tile(signal[None, :], [num_sweeps, 1])

        data = np.rint(data)

        return info, data


def lfilter_simple(x, sf):
    y = np.zeros_like(x)
    y[0] = x[0]

    for i in range(1, len(x)):
        y[i] = sf * y[i - 1] + (1 - sf) * x[i]

    return y


def filtfilt_simple(x, sf):
    return np.flip(lfilter_simple(np.flip(lfilter_simple(x, sf)), sf))


MOCK_CLASS_MAP = {
    Mode.ENVELOPE: EnvelopeMocker,
    Mode.IQ: IQMocker,
    Mode.SPARSE: SparseMocker,
    Mode.POWER_BINS: PowerBinMocker,
}
