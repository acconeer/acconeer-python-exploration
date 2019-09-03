import numpy as np
from scipy.signal import butter, filtfilt
from time import time, sleep
import logging

from acconeer_utils.clients.base import BaseClient, ClientError


log = logging.getLogger(__name__)


class MockClient(BaseClient):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _connect(self):
        pass

    def _setup_session(self, config):
        self._config = config

        try:
            mock_class = mock_class_map[config.mode]
        except KeyError as e:
            raise ClientError("mode not supported") from e

        self._mocker = mock_class(config)

        return self._mocker.session_info

    def _start_streaming(self):
        self._start_time = time()
        self._data_count = 0

    def _get_next(self):
        config = self._config

        self._data_count += 1

        data_capture_time = self._data_count / config.sweep_rate
        now = time() - self._start_time
        if data_capture_time > now:
            sleep(data_capture_time - now)

        args = (data_capture_time, self._data_count)
        num_sensors = len(config.sensor)

        if self.squeeze and num_sensors == 1:
            return self._mocker.get_next(*args, 0)
        else:
            idx_offset = max(0, (num_sensors - 1) / 2)
            out = [self._mocker.get_next(*args, i - idx_offset) for i in range(num_sensors)]
            info, data = zip(*out)
            data = np.array(data)
            info = list(info)

        return info, data

    def _stop_streaming(self):
        pass

    def _disconnect(self):
        pass


class DenseMocker:
    BASE_STEP_LENGTH = 0.485e-3

    def __init__(self, config):
        self.config = config

        self.num_depths = int(round(config.range_length / self.BASE_STEP_LENGTH)) + 1

        self.session_info = {
            "actual_range_start": config.range_start,
            "actual_range_length": config.range_length,
            "data_length": self.num_depths,
        }

        self.range_center = config.range_start + config.range_length / 2
        self.depths = np.linspace(*config.range_interval, self.num_depths)


class EnvelopeMocker(DenseMocker):
    def get_next(self, t, i, offset):
        info = {
            "data_saturated": False,
            "sequence_number": i,
        }

        noise = 100 + 20 * np.random.randn(self.num_depths)
        noise = filtfilt(*butter(2, 0.03), noise, method="gust")

        ampl = 2000 + np.random.randn() * 20
        center = self.range_center
        center += np.random.randn() * 0.2e-3
        center += offset * 0.1
        s = 0.01 if self.config.session_profile == self.config.MAX_DEPTH_RESOLUTION else 0.04
        signal = ampl * np.exp(-np.square((self.depths - center) / s))

        data = signal + noise

        return info, data


class IQMocker(DenseMocker):
    def get_next(self, t, i, offset):
        info = {
            "data_saturated": False,
            "sequence_number": i,
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
        data = filtfilt(*butter(2, 0.03), data, method="gust")

        return info, data


class PowerBinMocker(EnvelopeMocker):
    def __init__(self, config):
        self.config = config

        self.num_depths = config.bin_count or int(round(config.range_length / 0.1)) + 1

        self.session_info = {
            "actual_range_start": config.range_start,
            "actual_range_length": config.range_length,
            "data_length": self.num_depths,
            "actual_bin_count": self.num_depths,
        }

        self.range_center = config.range_start + config.range_length / 2
        self.depths = np.linspace(*config.range_interval, self.num_depths)


class SparseMocker:
    BASE_STEP_LENGTH = 0.06

    def __init__(self, config):
        self.config = config

        start_point = int(round(config.range_start / self.BASE_STEP_LENGTH))
        end_point = int(round(config.range_end / self.BASE_STEP_LENGTH))

        self.num_depths = end_point - start_point + 1

        start = start_point * self.BASE_STEP_LENGTH
        end = end_point * self.BASE_STEP_LENGTH

        self.session_info = {
            "actual_range_start": start,
            "actual_range_length": end - start,
            "data_length": self.num_depths * config.number_of_subsweeps,
        }

        self.range_center = (start + end) / 2
        self.depths = np.linspace(start, end, self.num_depths)

    def get_next(self, t, i, offset):
        info = {
            "data_saturated": False,
            "sequence_number": i,
        }

        num_subsweeps = self.config.number_of_subsweeps

        noise = 100 * np.random.randn(num_subsweeps, self.num_depths)

        xs = self.depths - self.range_center + 0.1 * np.sin(t)
        signal = 5000 * np.exp(-np.square(xs / 0.1)) * np.sin(xs / 2.5e-3)

        data = noise + np.tile(signal[None, :], [num_subsweeps, 1])

        return info, data


mock_class_map = {
    "envelope": EnvelopeMocker,
    "iq": IQMocker,
    "sparse": SparseMocker,
    "power_bin": PowerBinMocker,
}
