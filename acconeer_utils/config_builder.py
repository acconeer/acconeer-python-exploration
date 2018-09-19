from copy import copy


class ConfigBuilder:
    SERVICE_ENVELOPE = "envelope_data"
    SERVICE_IQ = "iq_data"
    VALID_SERVICES = [SERVICE_ENVELOPE, SERVICE_IQ]

    def __init__(self):
        self._service = self.SERVICE_ENVELOPE
        self._sensors = [1]
        self._range_start = 0.20
        self._range_length = 0.10
        self._sweep_count = None
        self._frequency = None
        self._gain = None

    @property
    def config(self):
        d = {
            "cmd": self._service,
            "sensors": self._sensors,
            "start_range": self.range_start,
            "end_range": self._range_end,
            "sweep_count": self._sweep_count,
            "frequency": self._frequency,
            "gain": self._gain,
        }
        return {k: v for k, v in d.items() if v is not None}

    @property
    def _range_end(self):
        return self._range_start + self._range_length

    @property
    def service(self):
        return self._service

    @service.setter
    def service(self, service):
        if service not in self.VALID_SERVICES:
            raise ValueError("{} is not a valid service".format(service))
        self._service = service

    @property
    def sensors(self):
        return self._sensors

    @sensors.setter
    def sensors(self, arg):
        if isinstance(arg, int):
            arg = [arg]
        elif isinstance(arg, list) and all([isinstance(e, int) for e in arg]):
            arg = copy(arg)
        else:
            raise TypeError("given sensor(s) must be either an int or a list of ints")
        self._sensors = arg

    @property
    def sweep_count(self):
        return self._sweep_count

    @sweep_count.setter
    def sweep_count(self, count):
        if not isinstance(count, int):
            raise TypeError("sweep count must be an int")
        if count < 0:
            raise ValueError("sweep count must be greater than 0")
        self._sweep_count = count

    @property
    def sweep_frequency(self):
        return self._frequency

    @sweep_frequency.setter
    def sweep_frequency(self, frequency):
        if not isinstance(frequency, int):
            raise TypeError("sweep frequency must be a number")
        if frequency < 1:
            raise ValueError("sweep freqeuncy must be greater or equal to 1")
        self._frequency = frequency

    @property
    def range_start(self):
        return self._range_start

    @range_start.setter
    def range_start(self, start):
        if start < 0:
            raise ValueError("invalid range start")
        self._range_start = start

    @property
    def range_length(self):
        return self._range_length

    @range_length.setter
    def range_length(self, length):
        if length < 0:
            raise ValueError("invalid range length")
        self._range_length = length

    @property
    def gain(self):
        return self._gain

    @gain.setter
    def gain(self, gain):
        if not 0 <= gain <= 1:
            raise ValueError("gain must be between 0 and 1")
        self._gain = gain
