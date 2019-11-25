import abc
import enum
from copy import copy

import numpy as np

from acconeer.exptool.modes import Mode


class ConfigEnum(enum.Enum):
    @property
    def label(self):
        return self.value[0]

    @property
    def json_value(self):
        return self.value[1]


class BaseSessionConfig(abc.ABC):
    _sensors = [1]

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if not hasattr(self.__class__, k):
                raise KeyError("unknown setting: {}".format(k))
            setattr(self, k, v)

    def __setattr__(self, name, value):
        if hasattr(self, name):
            object.__setattr__(self, name, value)
        else:
            raise AttributeError("{} has no setting {}".format(self.__class__.__name__, name))

    def __str__(self):
        attrs = [a for a in dir(self) if not a.startswith("_") and a.islower()]
        vals = [getattr(self, a) for a in attrs]
        d = {a: ("-" if v is None else v) for a, v in zip(attrs, vals)}
        s = self.__class__.__name__
        s += "".join(["\n  {:.<25} {}".format(a + " ", v) for (a, v) in d.items()])
        return s

    @property
    @abc.abstractmethod
    def mode(self):
        pass

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
            raise TypeError("sensor(s) must be an int or a list of ints")
        self._sensors = arg


class BaseServiceConfig(BaseSessionConfig):
    class RepetitionMode(ConfigEnum):
        HOST_DRIVEN = ("Host driven", "on_demand")
        SENSOR_DRIVEN = ("Sensor driven", "streaming")

    class Profile(ConfigEnum):
        PROFILE_1 = ("1 (max resolution)", 1)
        PROFILE_2 = ("2", 2)
        PROFILE_3 = ("3", 3)
        PROFILE_4 = ("4", 4)
        PROFILE_5 = ("5 (max SNR)", 5)

    _range_start = 0.2
    _range_length = 0.6
    _repetition_mode = RepetitionMode.HOST_DRIVEN
    _update_rate = None
    _gain = 0.5
    _hw_accelerated_average_samples = 10
    _maximize_signal_attenuation = False
    _profile = Profile.PROFILE_2

    @property
    def range_start(self):
        return self._range_start

    @range_start.setter
    def range_start(self, start):
        start = float(start)
        self._range_start = start

    @property
    def range_length(self):
        return self._range_length

    @range_length.setter
    def range_length(self, length):
        length = float(length)
        if length < 0.0:
            raise ValueError("range_length must be >= 0.0")
        self._range_length = length

    @property
    def range_end(self):
        if None in [self._range_start, self._range_length]:
            return None
        return self._range_start + self._range_length

    @range_end.setter
    def range_end(self, end):
        end = float(end)
        self.range_length = end - self.range_start

    @property
    def range_interval(self):
        return np.array([self.range_start, self.range_end])

    @range_interval.setter
    def range_interval(self, interval):
        start, end = interval
        start = float(start)
        end = float(end)
        self.range_start = start
        self.range_end = end

    @property
    def repetition_mode(self):
        return self._repetition_mode

    @repetition_mode.setter
    def repetition_mode(self, repetition_mode):
        if not isinstance(repetition_mode, self.RepetitionMode):
            raise TypeError("repetition_mode must be of type RepetitionMode")
        self._repetition_mode = repetition_mode

    @property
    def update_rate(self):
        return self._update_rate

    @update_rate.setter
    def update_rate(self, rate):
        if rate is not None:
            rate = float(rate)
            if rate <= 0.0:
                raise ValueError("update_rate must None or > 0")
        self._update_rate = rate

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        gain = float(gain)
        if not 0.0 <= gain <= 1.0:
            raise ValueError("gain must be between 0.0 and 1.0")
        self._gain = gain

    @property
    def hw_accelerated_average_samples(self):
        return self._hw_accelerated_average_samples

    @hw_accelerated_average_samples.setter
    def hw_accelerated_average_samples(self, hwaas):
        hwaas = int(hwaas)
        if not 1 <= hwaas <= 63:
            raise ValueError("hw_accelerated_average_samples must be between 1 and 63, inclusive")
        self._hw_accelerated_average_samples = hwaas

    @property
    def maximize_signal_attenuation(self):
        return self._maximize_signal_attenuation

    @maximize_signal_attenuation.setter
    def maximize_signal_attenuation(self, enabled):
        enabled = bool(enabled)
        self._maximize_signal_attenuation = enabled

    @property
    def profile(self):
        return self._profile

    @profile.setter
    def profile(self, profile):
        if not isinstance(profile, self.Profile):
            raise ValueError("profile must be of type Profile")
        self._profile = profile


class BaseDenseServiceConfig(BaseServiceConfig):
    _downsampling_factor = 1
    _noise_level_normalization = True

    @property
    def downsampling_factor(self):
        return self._downsampling_factor

    @downsampling_factor.setter
    def downsampling_factor(self, factor):
        factor = int(factor)
        if factor not in [1, 2, 4]:
            raise ValueError("downsampling_factor must be 1, 2, or 4")
        self._downsampling_factor = factor

    @property
    def noise_level_normalization(self):
        return self._noise_level_normalization

    @noise_level_normalization.setter
    def noise_level_normalization(self, enabled):
        enabled = bool(enabled)
        self._noise_level_normalization = enabled


class PowerBinServiceConfig(BaseDenseServiceConfig):
    _bin_count = None

    @property
    def mode(self):
        return Mode.POWER_BINS

    @property
    def bin_count(self):
        return self._bin_count

    @bin_count.setter
    def bin_count(self, count):
        if count is not None:
            count = int(count)
            if count <= 0:
                raise ValueError("bin_count must be None or > 0")
        self._bin_count = count


class EnvelopeServiceConfig(BaseDenseServiceConfig):
    _running_average_factor = 0.7

    @property
    def mode(self):
        return Mode.ENVELOPE

    @property
    def running_average_factor(self):
        return self._running_average_factor

    @running_average_factor.setter
    def running_average_factor(self, factor):
        factor = float(factor)
        if not (0 <= factor < 1):
            raise ValueError("running_average_factor must be between 0.0 and 1.0")
        self._running_average_factor = factor


class IQServiceConfig(BaseDenseServiceConfig):
    class SamplingMode(ConfigEnum):
        A = ("A", 0)
        B = ("B", 1)

    _sampling_mode = SamplingMode.A

    @property
    def mode(self):
        return Mode.IQ

    @property
    def sampling_mode(self):
        return self._sampling_mode

    @sampling_mode.setter
    def sampling_mode(self, mode):
        if not isinstance(mode, self.SamplingMode):
            raise ValueError("sampling_mode must be of type SamplingMode")
        self._sampling_mode = mode


class SparseServiceConfig(BaseServiceConfig):
    class SamplingMode(ConfigEnum):
        A = ("A", 0)
        B = ("B", 1)

    _sweeps_per_frame = 16
    _sweep_rate = None
    _sampling_mode = SamplingMode.B
    _downsampling_factor = 1

    @property
    def mode(self):
        return Mode.SPARSE

    @property
    def sweeps_per_frame(self):
        return self._sweeps_per_frame

    @sweeps_per_frame.setter
    def sweeps_per_frame(self, sweeps_per_frame):
        sweeps_per_frame = int(sweeps_per_frame)
        if sweeps_per_frame < 1:
            raise ValueError("sweeps_per_frame must be at least 1")
        self._sweeps_per_frame = sweeps_per_frame

    @property
    def sweep_rate(self):
        return self._sweep_rate

    @sweep_rate.setter
    def sweep_rate(self, rate):
        if rate is not None:
            rate = float(rate)
            if rate <= 0.0:
                raise ValueError("sweep_rate must None or > 0")
        self._sweep_rate = rate

    @property
    def sampling_mode(self):
        return self._sampling_mode

    @sampling_mode.setter
    def sampling_mode(self, mode):
        if not isinstance(mode, self.SamplingMode):
            raise ValueError("sampling_mode must be of type SamplingMode")
        self._sampling_mode = mode

    @property
    def downsampling_factor(self):
        return self._downsampling_factor

    @downsampling_factor.setter
    def downsampling_factor(self, factor):
        factor = int(factor)
        if factor < 1:
            raise ValueError("downsampling_factor must be at least 1")
        self._downsampling_factor = factor


MODE_TO_CONFIG_CLASS_MAP = {
    Mode.POWER_BINS: PowerBinServiceConfig,
    Mode.ENVELOPE: EnvelopeServiceConfig,
    Mode.IQ: IQServiceConfig,
    Mode.SPARSE: SparseServiceConfig,
}
