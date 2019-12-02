import enum

import acconeer.exptool.structs.configbase as cb
from acconeer.exptool.modes import Mode


class ConfigEnum(enum.Enum):
    @property
    def label(self):
        return self.value[0]

    @property
    def json_value(self):
        return self.value[1]


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
        default_value=[0.18, 0.78],
        limits=(-0.7, 7.0),
        order=10,
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
    )

    gain = cb.FloatParameter(
        label="Gain",
        default_value=0.5,
        limits=(0.0, 1.0),
        decimals=2,
        order=1040,
        category=cb.Category.ADVANCED,
    )

    hw_accelerated_average_samples = cb.IntParameter(
        label="HW accel. average samples",
        default_value=10,
        limits=(1, 63),
        order=1030,
        category=cb.Category.ADVANCED,
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
    )

    def check(self):
        alerts = []

        if self.repetition_mode == __class__.RepetitionMode.SENSOR_DRIVEN:
            if self.update_rate is None:
                alerts.append(cb.Error("update_rate", "Must be set when sensor driven"))

        if self.gain > 0.9:
            alerts.append(cb.Warning("gain", "Too high gain causes degradation"))

        if self.range_start < self.profile.approx_direct_leakage_length:
            alerts.append(cb.Warning("range_interval", "Direct leakage might be seen"))

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

        if self.downsampling_factor not in [1, 2, 4]:
            alerts.append(cb.Error("downsampling_factor", "Must be 1, 2, or 4"))

        return alerts


class PowerBinServiceConfig(BaseDenseServiceConfig):
    mode = cb.ConstantParameter(
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
        return alerts


class EnvelopeServiceConfig(BaseDenseServiceConfig):
    mode = cb.ConstantParameter(
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

    mode = cb.ConstantParameter(
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
        return alerts


class SparseServiceConfig(BaseServiceConfig):
    class SamplingMode(ConfigEnum):
        A = ("A (less correlation)", 0)
        B = ("B (more SNR)", 1)

    mode = cb.ConstantParameter(
        label="Mode",
        value=Mode.SPARSE,
    )

    sweeps_per_frame = cb.IntParameter(
        label="Sweeps per frame",
        default_value=16,
        limits=(1, 2048),
        order=50,
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
    )

    sampling_mode = cb.EnumParameter(
        label="Sampling mode",
        enum=SamplingMode,
        default_value=SamplingMode.B,
        order=1000,
        category=cb.Category.ADVANCED,
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

        return alerts


MODE_TO_CONFIG_CLASS_MAP = {
    Mode.POWER_BINS: PowerBinServiceConfig,
    Mode.ENVELOPE: EnvelopeServiceConfig,
    Mode.IQ: IQServiceConfig,
    Mode.SPARSE: SparseServiceConfig,
}
