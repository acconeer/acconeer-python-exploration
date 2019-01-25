from abc import ABCMeta, abstractmethod
from copy import copy
import numpy as np


class BaseSessionConfig(metaclass=ABCMeta):
    def __init__(self, **kwargs):
        self._sweep_rate = None
        self._sensors = [1]

        for k, v in kwargs.items():
            if not hasattr(self.__class__, k):
                raise KeyError("unknown setting: {}".format(k))
            setattr(self, k, v)

    @property
    def sweep_rate(self):
        return self._sweep_rate

    @sweep_rate.setter
    def sweep_rate(self, rate):
        if rate < 1:
            raise ValueError("sweep rate must be >= 1")
        self._sweep_rate = rate

    @property
    def sensor(self):
        return self._sensors

    @sensor.setter
    def sensor(self, arg):
        if isinstance(arg, int):
            arg = [arg]
        elif isinstance(arg, list) and all([isinstance(e, int) for e in arg]):
            arg = copy(arg)
        else:
            raise TypeError("given sensor(s) must be either an int or a list of ints")
        self._sensors = arg

    @property
    @abstractmethod
    def mode(self):
        pass

    def __str__(self):
        attrs = [a for a in dir(self) if not a.startswith("_")]
        vals = [getattr(self, a) or "-" for a in attrs]
        d = {a: ("-" if v is None else v) for a, v in zip(attrs, vals)}
        s = self.__class__.__name__
        s += "".join(["\n  {:.<25} {}".format(a+" ", v) for (a, v) in d.items()])
        return s


class BaseServiceConfig(BaseSessionConfig):
    def __init__(self, **kwargs):
        self._gain = None
        self._range_start = None
        self._range_length = None
        super().__init__(**kwargs)

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        if not 0 <= gain <= 1:
            raise ValueError("gain must be between 0 and 1")
        self._gain = gain

    @property
    def range_start(self):
        return self._range_start

    @range_start.setter
    def range_start(self, start):
        if start < 0:
            raise ValueError("range start must be positive")
        self._range_start = start

    @property
    def range_length(self):
        return self._range_length

    @range_length.setter
    def range_length(self, length):
        if length < 0:
            raise ValueError("range length must be positive")
        self._range_length = length

    @property
    def range_interval(self):
        if None in [self._range_start, self._range_length]:
            return None
        return np.array([self.range_start, self.range_end])

    @range_interval.setter
    def range_interval(self, interval):
        start, end = interval
        self.range_start = start
        self.range_length = end - start

    @property
    def range_end(self):
        if None in [self._range_start, self._range_length]:
            return None
        return self._range_start + self._range_length

    @range_end.setter
    def range_end(self, range_end):
        self.range_length = range_end - self.range_start


class BaseDenseServiceConfig(BaseServiceConfig):
    def __init__(self, **kwargs):
        self._running_average_factor = None
        super().__init__(**kwargs)

    @property
    def running_average_factor(self):
        return self._running_average_factor

    @running_average_factor.setter
    def running_average_factor(self, factor):
        if not (0 < factor < 1):
            raise ValueError("running average factor must be between 0 and 1")
        self._running_average_factor = factor


class PowerBinServiceConfig(BaseServiceConfig):
    def __init__(self, **kwargs):
        self._bin_count = None
        super().__init__(**kwargs)

    @property
    def mode(self):
        return "power_bin"

    @property
    def bin_count(self):
        return self._bin_count

    @bin_count.setter
    def bin_count(self, count):
        if count <= 0:
            raise ValueError("bin count must be > 0")
        self._bin_count = count


class EnvelopeServiceConfig(BaseDenseServiceConfig):
    MAX_DEPTH_RESOLUTION = 0
    MAX_SNR = 1

    def __init__(self, **kwargs):
        self._session_profile = None
        self._compensate_phase = None
        super().__init__(**kwargs)

    @property
    def mode(self):
        return "envelope"

    @property
    def compensate_phase(self):
        return self._compensate_phase

    @compensate_phase.setter
    def compensate_phase(self, enabled):
        self._compensate_phase = enabled

    @property
    def session_profile(self):
        return self._session_profile

    @session_profile.setter
    def session_profile(self, profile):
        if profile not in [self.MAX_DEPTH_RESOLUTION, self.MAX_SNR]:
            raise ValueError("invalid profile")
        self._session_profile = profile


class IQServiceConfig(BaseDenseServiceConfig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def mode(self):
        return "iq"


class DistancePeakDetectorConfig(BaseServiceConfig):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def mode(self):
        return "distance_peak_fix_threshold"
