import enum

import acconeer.exptool.structs.configbase as cb
from acconeer.exptool.modes import Mode, get_mode


class ConfigEnum(enum.Enum):
    @property
    def label(self):
        return self.value[0]

    @property
    def json_value(self):
        return self.value[1]


class ModeParameter(cb.ConstantParameter):
    def __init__(self, **kwargs):
        assert isinstance(kwargs["value"], Mode)
        kwargs.setdefault("does_dump", True)
        super().__init__(**kwargs)

    def dump(self, obj):
        return self.__get__(obj).name

    def load(self, obj, value):
        assert get_mode(value) == self.value


class BaseSessionConfig(cb.SensorConfig):
    sensor = cb.SensorParameter(
        label="Sensor(s)",
        default_value=[1],
        order=0,
    )


class BaseServiceConfig(BaseSessionConfig):
    class RepetitionMode(ConfigEnum):
        HOST_DRIVEN = ("Host driven", "on_demand")
        SENSOR_DRIVEN = ("Sensor driven", "streaming")

    class Profile(ConfigEnum):
        PROFILE_1 = ("1 (max resolution)", 1, 0.10)
        PROFILE_2 = ("2", 2, 0.12)
        PROFILE_3 = ("3", 3, 0.18)
        PROFILE_4 = ("4", 4, 0.36)
        PROFILE_5 = ("5 (max SNR)", 5, 0.60)

        @property
        def approx_direct_leakage_length(self):
            return self.value[2]

    range_interval = cb.FloatRangeParameter(
        label="Range interval",
        unit="m",
        default_value=[0.18, 0.78],
        limits=(-0.7, 7.0),
        order=10,
        help=r"""
            The measured depth range. The start and end values will be rounded to the closest
            measurement point available.
        """,
    )

    range_start = cb.get_virtual_parameter_class(cb.FloatParameter)(
        label="Range start",
        get_fun=lambda conf: conf.range_interval[0],
        visible=False,
    )

    range_length = cb.get_virtual_parameter_class(cb.FloatParameter)(
        label="Range length",
        get_fun=lambda conf: conf.range_interval[1] - conf.range_interval[0],
        visible=False,
    )

    range_end = cb.get_virtual_parameter_class(cb.FloatParameter)(
        label="Range end",
        get_fun=lambda conf: conf.range_interval[1],
        visible=False,
    )

    repetition_mode = cb.EnumParameter(
        label="Repetition mode",
        enum=RepetitionMode,
        default_value=RepetitionMode.HOST_DRIVEN,
        order=1010,
        category=cb.Category.ADVANCED,
    )

    update_rate = cb.FloatParameter(
        label="Update rate",
        unit="Hz",
        default_value=None,
        limits=(0.1, None),
        decimals=1,
        optional=True,
        optional_label="Limit",
        optional_default_set_value=50.0,
        order=30,
        help=r"""
            The data frame rate :math:`f_f` from the service.

            .. attention::

               Setting the update rate too high might result in missed data frames.

            In sparse, the maximum possible update rate depends on the *sweeps per frame*
            :math:`N_s` and *sweep rate* :math:`f_s`:

            .. math::

               \frac{1}{f_f} > N_s \cdot \frac{1}{f_s} + \text{overhead*}

            \* *The overhead largely depends on data frame size and data transfer speeds.*
        """
    )

    gain = cb.FloatParameter(
        label="Gain",
        default_value=0.5,
        limits=(0.0, 1.0),
        decimals=2,
        order=1040,
        category=cb.Category.ADVANCED,
        help=r"""
            The receiver gain used in the sensor. If the gain is too low, objects may not be
            visible, or it may result in poor signal quality due to quantization errors. If the
            gain is too high, strong reflections may saturate the data. We recommend not setting
            the gain higher than necessary due to signal quality reasons.

            Must be between 0 and 1 inclusive, where 1 is the highest possible gain.
        """,
    )

    hw_accelerated_average_samples = cb.IntParameter(
        label="HW accel. average samples",
        default_value=10,
        limits=(1, 63),
        order=1030,
        category=cb.Category.ADVANCED,
        help=r"""
            Number of samples taken to obtain a single point in the data. These are averaged
            directly in the sensor hardware - no extra computations are done in the MCU.

            The time needed to measure a sweep is roughly proportional to the HWAAS. Hence, if
            there's a need to obtain a higher sweep rate, HWAAS could be decreased.

            Must be at least 1 and not greater than 63.
        """,
    )

    maximize_signal_attenuation = cb.BoolParameter(
        label="Max signal attenuation",
        default_value=False,
        order=2000,
        category=cb.Category.ADVANCED,
    )

    profile = cb.EnumParameter(
        label="Profile",
        enum=Profile,
        default_value=Profile.PROFILE_2,
        order=20,
    )

    downsampling_factor = cb.IntParameter(
        label="Downsampling factor",
        default_value=1,
        limits=(1, None),
        order=1020,
        category=cb.Category.ADVANCED,
        help=r"""
            The range downsampling by an integer factor. A factor of 1 means no downsampling, thus
            sampling with the smallest possible depth interval. A factor 2 samples every other
            point, and so on. In Envelope and IQ, the finest interval is ~0.5 mm. In Power Bins,
            it is the same but then further downsampled in post-processing.
            In sparse, it is ~6 cm.

            The downsampling is performed by skipping measurements in the sensor, and therefore
            gives lower memory usage, lower power consumption, and lower duty cycle.

            In sparse, setting a too large factor might result in gaps in the data where moving
            objects "disappear" between sampling points.

            In Envelope, IQ, and Power Bins, the factor must be 1, 2, or 4.
            In sparse, it must be at least 1.
            Setting a factor greater than 1 might affect the range end point.
        """,
    )

    def check(self):
        alerts = []

        if self.repetition_mode == __class__.RepetitionMode.SENSOR_DRIVEN:
            if self.update_rate is None:
                alerts.append(cb.Error("update_rate", "Must be set when sensor driven"))

        if self.gain > 0.9:
            alerts.append(cb.Warning("gain", "Too high gain causes degradation"))

        if self.range_start < self.profile.approx_direct_leakage_length:
            alerts.append(cb.Info("range_interval", "Direct leakage might be seen"))

        return alerts


class BaseDenseServiceConfig(BaseServiceConfig):
    noise_level_normalization = cb.BoolParameter(
        label="Noise level normalization",
        default_value=True,
        order=2010,
        category=cb.Category.ADVANCED,
    )

    def check(self):
        alerts = super().check()

        if self.range_length < 1e-6:
            alerts.append(cb.Warning("range_interval", "Will only return a single point"))

        if self.downsampling_factor not in [1, 2, 4]:
            alerts.append(cb.Error("downsampling_factor", "Must be 1, 2, or 4"))

        if self.repetition_mode == __class__.RepetitionMode.SENSOR_DRIVEN:
            chunks = self.range_length / 0.06
            chunks += 2 if self.mode == Mode.IQ else 0
            points_per_chunk = 124 / self.downsampling_factor
            if points_per_chunk * chunks > 2048:
                alerts.append(cb.Error("range_interval", "Too large for buffer"))

        return alerts


class PowerBinServiceConfig(BaseDenseServiceConfig):
    _MIN_BIN_SIZE = 0.016

    mode = ModeParameter(
        label="Mode",
        value=Mode.POWER_BINS,
    )

    bin_count = cb.IntParameter(
        label="Bin count",
        default_value=5,
        limits=(1, None),
        order=5,
    )

    def check(self):
        alerts = super().check()

        if self.range_length < self._MIN_BIN_SIZE:
            alerts.append(cb.Error("range_interval", "Too short"))
        elif self.range_length / self.bin_count < self._MIN_BIN_SIZE:
            alerts.append(cb.Error("bin_count", "Too high for current range"))

        return alerts


class EnvelopeServiceConfig(BaseDenseServiceConfig):
    mode = ModeParameter(
        label="Mode",
        value=Mode.ENVELOPE,
    )

    running_average_factor = cb.FloatParameter(
        label="Running avg. factor",
        default_value=0.7,
        limits=(0.0, 1.0),
        order=500,
    )

    def check(self):
        alerts = super().check()
        return alerts


class IQServiceConfig(BaseDenseServiceConfig):
    class SamplingMode(ConfigEnum):
        A = ("A (less correlation)", 0)
        B = ("B (more SNR)", 1)

    mode = ModeParameter(
        label="Mode",
        value=Mode.IQ,
    )

    sampling_mode = cb.EnumParameter(
        label="Sampling mode",
        enum=SamplingMode,
        default_value=SamplingMode.A,
        order=1000,
        category=cb.Category.ADVANCED,
    )

    def check(self):
        alerts = super().check()

        if self.range_start < (0.06 - 1e-6):
            alerts.append(cb.Error("range_interval", "Start must be >= 0.06 m"))

        return alerts


class SparseServiceConfig(BaseServiceConfig):
    class SamplingMode(ConfigEnum):
        A = ("A (less correlation)", 0)
        B = ("B (more SNR)", 1)

    mode = ModeParameter(
        label="Mode",
        value=Mode.SPARSE,
    )

    sweeps_per_frame = cb.IntParameter(
        label="Sweeps per frame",
        default_value=16,
        limits=(1, 2048),
        order=50,
        help=r"""
            The number of sweeps per frame :math:`N_s`.

            Must be at least 1, and not greater than 64 when using sampling mode B.
        """,
    )

    sweep_rate = cb.FloatParameter(
        label="Sweep rate",
        unit="Hz",
        default_value=None,
        limits=(1, None),
        decimals=0,
        optional=True,
        optional_default_set_value=3000.0,
        order=40,
        help=r"""
            The sparse sweep rate :math:`f_s`. If not set, this will take the maximum possible
            value.

            The maximum possible sweep rate...

            - Is roughly inversely proportional to the number of depth points measured (affected
              by the **range interval** and **downsampling factor**).
            - Is roughly inversely proportional to **HW accelerated average samples**.
            - Depends on the **sampling mode**. Mode A is roughly :math:`4/3 \approx 130\%` slower
              than mode B with the same configuration.

            To get the maximum possible rate, leave this value unset and look at the :ref:`sweep
            rate <sparse-info-sweep-rate>` in the session info (metadata).

            .. tip::
               If you do not need a specific sweep rate, we recommend leaving it unset.
        """,
    )

    sampling_mode = cb.EnumParameter(
        label="Sampling mode",
        enum=SamplingMode,
        default_value=SamplingMode.B,
        order=1000,
        category=cb.Category.ADVANCED,
        help=r"""
            The sampling mode changes how the hardware accelerated averaging is done. Mode A is
            optimized for maximal independence of the depth points, giving a higher depth
            resolution than mode B. Mode B is instead optimized for maximal SNR per unit time
            spent on measuring. This makes it more energy efficient and suitable for cases where
            small movements are to be detected over long ranges. Mode A is more suitable for
            applications like gesture recognition, measuring the distance to a movement, and
            speed measurements.

            Mode B typically gives roughly 3 dB better SNR per unit time than mode A. However,
            please note that very short ranges of only one or a few points are suboptimal with
            mode B. In those cases, always use mode A.
        """,
    )

    def check(self):
        alerts = super().check()

        if self.sampling_mode == __class__.SamplingMode.B:
            if self.sweeps_per_frame > 64:
                alerts.append(cb.Error("sweeps_per_frame", "Must be < 64 with sampling mode B"))

        if self.sweep_rate is not None and self.update_rate is not None:
            max_frame_rate = self.sweep_rate / self.sweeps_per_frame

            if self.update_rate > max_frame_rate:
                alerts.append(cb.Error("sweep_rate", "Too low for current update rate"))

        # Pessimistic buffer size check
        start_p = int(round(self.range_start / 0.06 - 0.01))
        end_p = int(round(self.range_end / 0.06 + 0.01))
        sweep_size = (end_p - start_p) // self.downsampling_factor + 1
        if sweep_size * self.sweeps_per_frame > 2048:
            alerts.append(cb.Error("range_interval", "Too long for buffer"))

        return alerts


MODE_TO_CONFIG_CLASS_MAP = {
    Mode.POWER_BINS: PowerBinServiceConfig,
    Mode.ENVELOPE: EnvelopeServiceConfig,
    Mode.IQ: IQServiceConfig,
    Mode.SPARSE: SparseServiceConfig,
}
