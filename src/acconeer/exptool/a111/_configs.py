# Copyright (c) Acconeer AB, 2022
# All rights reserved

import enum
import json

import acconeer.exptool._structs.configbase as cb
from acconeer.exptool import utils
from acconeer.exptool.a111._modes import Mode, get_mode


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
        help=r"""
            The sensor(s) to be configured.
        """,
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

    class PowerSaveMode(ConfigEnum):
        ACTIVE = ("Active", "active")
        READY = ("Ready", "ready")
        SLEEP = ("Sleep", "sleep")
        HIBERNATE = ("Hibernate", "hibernate")
        OFF = ("Off", "off")

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
        help=r"""
            The RSS supports two different repetition modes. They determine how and when data
            acquisition occurs. They are:

            * **On demand / host driven**: The sensor produces data when requested by the
              application. Hence, the application is responsible for timing the data acquisition.
              This is the default mode, and may be used with all power save modes.

            * **Streaming / sensor driven**: The sensor produces data at a fixed rate, given by a
              configurable accurate hardware timer. This mode is recommended if exact timing
              between updates is required.

            The Exploration Tool is capable of setting the update rate also in *on demand (host
            driven)* mode. Thus, the difference between the modes becomes subtle. This is why *on
            demand* and *streaming* are called *host driven* and *sensor driven* respectively in
            Exploration Tool.
        """,
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
            The rate :math:`f_f` at which the sensor sends frames to the host MCU.

            .. attention::

               Setting the update rate too high might result in missed data frames.

            In sparse, the maximum possible update rate depends on the *sweeps per frame*
            :math:`N_s` and *sweep rate* :math:`f_s`:

            .. math::

               \frac{1}{f_f} > N_s \cdot \frac{1}{f_s} + \text{overhead*}

            \* *The overhead largely depends on data frame size and data transfer speeds.*
        """,
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
            gain is too high, strong reflections may result in saturated data. We recommend not
            setting the gain higher than necessary due to signal quality reasons.

            Must be between 0 and 1 inclusive, where 1 is the highest possible gain.

            .. note::
               When Sensor normalization is active, the change in the data due to changing gain is
               removed after normalization. Therefore, the data might seen unaffected by changes
               in the gain, except very high (receiver saturation) or very low (quantization
               error) gain.

               Sensor normalization is not available for the Sparse service, but is enabled by
               default for the other services - Envelope, IQ, and Power Bins.
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
            there's a need to obtain a higher sweep rate, HWAAS could be decreased. Note that
            HWAAS does not affect the amount of data transmitted from the sensor over SPI.

            Must be at least 1 and not greater than 63.
        """,
    )

    maximize_signal_attenuation = cb.BoolParameter(
        label="Max signal attenuation",
        default_value=False,
        order=2000,
        category=cb.Category.ADVANCED,
        help=r"""
            When measuring in the direct leakage (around 0m), this setting can be enabled to
            minimize saturation in the receiver. We do not recommend using this setting under
            normal operation.
        """,
    )

    profile = cb.EnumParameter(
        label="Profile",
        enum=Profile,
        default_value=Profile.PROFILE_2,
        order=20,
        help=r"""
            The main configuration of all the services are the profiles, numbered 1 to 5. The
            difference between the profiles is the length of the radar pulse and the way the
            incoming pulse is sampled. Profiles with low numbers use short pulses while the higher
            profiles use longer pulses.

            Profile 1 is recommended for:

            - measuring strong reflectors, to avoid saturation of the received signal
            - close range operation (<20 cm), due to the reduced direct leakage

            Profile 2 and 3 are recommended for:

            - operation at intermediate distances, (20 cm to 1 m)
            - where a balance between SNR and depth resolution is acceptable

            Profile 4 and 5 are recommended for:

            - for Sparse service only
            - operation at large distances (>1 m)
            - motion or presence detection, where an optimal SNR ratio is preferred over a high
              resolution distance measurement

            The previous profile Maximize Depth Resolution and Maximize SNR are now profile 1 and
            2. The previous Direct Leakage Profile is obtained by the use of the Maximize Signal
            Attenuation parameter.
        """,
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
            Setting a factor greater than 1 might affect the range end point and for IQ and
            Envelope, also the first point.
        """,
    )

    tx_disable = cb.BoolParameter(
        label="Disable TX",
        default_value=False,
        order=3000,
        category=cb.Category.ADVANCED,
        help=r"""
            Disable the radio transmitter. If used to measure noise, we recommended also switching
            off noise level normalization (if applicable).
        """,
    )

    power_save_mode = cb.EnumParameter(
        label="Power save mode",
        enum=PowerSaveMode,
        default_value=PowerSaveMode.ACTIVE,
        order=3100,
        category=cb.Category.ADVANCED,
        help=r"""
            The power save mode configuration sets what state the sensor waits in between
            measurements in an active service. There are five power save modes. The modes
            differentiate in current dissipation and response latency, where the most current
            consuming mode *Active* gives fastest response and the least current consuming mode
            *Off* gives the slowest response. The absolute response time and also maximum update
            rate is determined by several factors besides the power save mode configuration.

            In addition, the host capabilities in terms of SPI communication speed and
            processing speed also impact on the absolute response time. The power consumption of
            the system depends on the actual configuration of the application and it is recommended
            to test both maximum update rate and power consumption when the configuration
            is decided.

            ================== ==================== ==============
            Power save mode    Current consumption  Response time
            ================== ==================== ==============
            Off                Lowest               Longest
            Hibernate          ...                  ...
            Sleep              ...                  ...
            Ready              ...                  ...
            Active             Highest              Shortest
            ================== ==================== ==============

            .. note::
               Hibernation has limited hardware support. It is not supported by the Raspberry Pi
               EVK:s and XM112.
        """,
    )

    asynchronous_measurement = cb.BoolParameter(
        label="Enable asynchronous measurement",
        default_value=True,
        order=3200,
        category=cb.Category.ADVANCED,
        help=r"""
            Enabling asynchronous measurements will result in a faster update rate but introduces a
            risk of interference between sensors.
        """,
    )

    def check(self):
        alerts = []

        if self.repetition_mode == __class__.RepetitionMode.SENSOR_DRIVEN:
            msg = "Must be set when sensor driven"

            if self.update_rate is None:
                alerts.append(cb.Error("update_rate", msg))

            if not self.asynchronous_measurement:
                alerts.append(cb.Error("asynchronous_measurement", msg))

        if self.gain > 0.9:
            alerts.append(cb.Warning("gain", "Too high gain causes degradation"))

        if self.range_start < self.profile.approx_direct_leakage_length:
            alerts.append(cb.Info("range_interval", "Direct leakage might be seen"))

        if self.power_save_mode == __class__.PowerSaveMode.HIBERNATE:
            alerts.append(cb.Warning("power_save_mode", "Limited hardware support"))

            if self.repetition_mode == __class__.RepetitionMode.SENSOR_DRIVEN:
                alerts.append(cb.Error("power_save_mode", "Unavailable when sensor driven"))

        psms = [__class__.PowerSaveMode.HIBERNATE, __class__.PowerSaveMode.OFF]
        if self.power_save_mode in psms:
            if self.asynchronous_measurement:
                msg = "PSM hibernate/off is always synchronous"
                alerts.append(cb.Info("asynchronous_measurement", msg))

        return alerts


class BaseDenseServiceConfig(BaseServiceConfig):
    noise_level_normalization = cb.BoolParameter(
        label="Noise level normalization",
        default_value=True,
        order=2010,
        category=cb.Category.ADVANCED,
        help=r"""
            With the SW version 2 release, a sensor signal normalization functionality is activated
            by default for the Power Bins, Envelope, and IQ Service. This results in a more
            constant signal for different temperatures and sensors. The radar sweeps are normalized
            to have similar amplitude independent of sensor gain and hardware averaging, resulting
            in only minor visible effect in the sweeps when adjusting these parameters.

            We recommend this setting especially for applications, where absolute radar amplitudes
            are important, such as when comparing to a previously recorded signal or to a fixed
            threshold.

            More technically, the functionality is implemented to collect data when starting the
            service, but not transmitting pulses. This data is then used to determine the current
            sensitivity of receiving part of the radar by estimating the power level of the noise,
            which then is used to normalize the collected sweeps. In the most low-power systems,
            where a service is created to collect just a single short sweep before turning off, the
            sensor normalization can add a non-negligible part to the power consumption.

            Please note, that due to the nature of Sparse data, the Sparse service does not support
            noise level normalization. Instead, normalization during processing is recommended,
            such as done in the Presence detector.

        """,
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

        if self.power_save_mode == __class__.PowerSaveMode.HIBERNATE:
            alerts.append(cb.Error("power_save_mode", "Not supported for this service"))

        return alerts


class _MURCapable(cb.SensorConfig):
    class MUR(ConfigEnum):
        MUR_6 = ("6 (MMD: 7.0m)", 6, 7.0)
        MUR_9 = ("9 (MMD: 12.7m)", 9, 12.7)

        @property
        def mmd(self):
            return self.value[2]

    mur = cb.EnumParameter(
        label="Max. unambiguous range",
        enum=MUR,
        default_value=MUR.MUR_6,
        order=15,
        help=r"""
            Sets the *maximum unambiguous range* (MUR), which in turn sets the *maximum measurable
            distance* (MMD).

            The MMD is the maximum value for the range end, i.e., the range start + length. The MMD
            is smaller than the MUR due to hardware limitations.

            The MUR is the maximum distance at which an object can be located to guarantee that its
            reflection corresponds to the most recent transmitted pulse. Objects farther away than
            the MUR may fold into the measured range. For example, with a MUR of 10 m, an object at
            12 m could become visible at 2 m.

            A higher setting gives a larger MUR/MMD, but comes at a cost of increasing the
            measurement time for a sweep. The measurement time is approximately proportional to the
            MUR.

            This setting changes the *pulse repetition frequency* (PRF) of the radar system. The
            relation between PRF and MUR is

            .. math::

               \text{MUR} = c / (2 * \text{PRF})

            where *c* is the speed of light.

            =======  ======  ======  ========
            Setting     MUR     MMD       PRF
            =======  ======  ======  ========
                  6  11.5 m   7.0 m  13.0 MHz
                  9  17.3 m  12.7 m   8.7 MHz
            =======  ======  ======  ========

            This is an experimental feature.
        """,
    )

    range_interval = cb.FloatRangeParameter(
        label="Range interval",
        unit="m",
        default_value=[0.18, 0.78],
        limits=(-0.7, 12.7),
        order=10,
        help=r"""
            The measured depth range. The start and end values will be rounded to the closest
            measurement point available.

            The the sweep range is limited to 7.0 m for the default "maximum unambiguous range"
            setting. To change this limitation, increase "maximum unambiguous range".
        """,
    )

    def check(self):
        alerts = super().check()
        if self.mur.mmd < self.range_end:
            alerts.append(
                cb.Error(
                    "mur",
                    "Too low for the given range",
                )
            )
            alerts.append(
                cb.Error(
                    "range_interval",
                    f"MUR limits the range to {self.mur.mmd:.1f} m",
                )
            )
        return alerts


class PowerBinServiceConfig(_MURCapable, BaseDenseServiceConfig):
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
        help=r"""
            The number of bins to be used for creating the amplitude over distance histogram.
        """,
    )

    def check(self):
        alerts = super().check()

        if self.range_length < self._MIN_BIN_SIZE:
            alerts.append(cb.Error("range_interval", "Too short"))
        elif self.range_length / self.bin_count < self._MIN_BIN_SIZE:
            alerts.append(cb.Error("bin_count", "Too high for current range"))

        return alerts


class EnvelopeServiceConfig(_MURCapable, BaseDenseServiceConfig):
    mode = ModeParameter(
        label="Mode",
        value=Mode.ENVELOPE,
    )

    running_average_factor = cb.FloatParameter(
        label="Running avg. factor",
        default_value=0.7,
        limits=(0.0, 1.0),
        order=500,
        help=r"""
            The time smoothing factor for Envelope sweeps. With the running average factor
            larger than zero, consecutive sweeps are averaged using an exponential window
            function. A runnning average factor of 0.0 corresponds to no time filtering of
            sweeps and close to 1.0 results in more filtering.

            Envelope sweep number :math:`s` returned by RSS, :math:`E_s(r)`, is calculated from
            the measured sweep, :math:`e_s(r)`, according to

            .. math::

               E_s(r) = \text{RAF} \cdot E_{s-1}(r) + (1 - \text{RAF}) \cdot e_{s}(r),

            where RAF is the running average factor.
        """,
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
        is_dummy=True,
    )

    depth_lowpass_cutoff_ratio = cb.FloatParameter(
        label="Depth LPF cutoff ratio",
        default_value=None,
        limits=(0.0, 0.5),
        decimals=6,
        optional=True,
        optional_default_set_value=0.5,
        optional_label="Override",
        order=2100,
        category=cb.Category.ADVANCED,
        help=r"""
            Depth domain lowpass filter cutoff frequency ratio

            The cutoff for the depth domain lowpass filter is specified as the ratio between the
            spatial frequency cutoff and the sample frequency. A ratio of zero ratio will configure
            the smoothest possible filter. A ratio of 0.5 (the Nyquist frequency) turns the filter
            off.

            If unset, i.e., if not overridden, the ratio will be chosen automatically. The used
            ratio is returned in the session information (metadata) upon session setup (create).
        """,
    )

    _depth_lowpass_cutoff_ratio_value = cb.get_virtual_parameter_class(cb.FloatParameter)(
        label="Depth LPF cutoff ratio value",
        get_fun=lambda conf: utils.optional_or_else(conf.depth_lowpass_cutoff_ratio, 0.0),
        visible=False,
    )

    _depth_lowpass_cutoff_ratio_override = cb.get_virtual_parameter_class(cb.BoolParameter)(
        label="Depth LPF cutoff ratio override",
        get_fun=lambda conf: conf.depth_lowpass_cutoff_ratio is not None,
        visible=False,
    )

    def check(self):
        alerts = super().check()

        if self.range_start < (0.06 - 1e-6):
            alerts.append(cb.Error("range_interval", "Start must be >= 0.06 m"))

        if self.sampling_mode == __class__.SamplingMode.B:
            alerts.append(cb.Error("sampling_mode", "IQ sampling mode B is removed"))

        return alerts


class SparseServiceConfig(_MURCapable, BaseServiceConfig):
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
            In Sparse, each frame is a collection of several sweeps over the selected distance
            range (sweeps per frame). The sweep rate :math:`f_s` is the rate at which sweeps are
            performed, i.e. the rate at which each distance point is scanned. If you set the sweep
            rate to 4000 Hz and the sweeps per frame to 32, each Sparse data frame will contain 32
            sweeps over the selected distance range, where the sweeps are measured at a rate of
            4000 Hz.

            The maximum possible sweep rate...

            - Is roughly inversely proportional to the number of depth points measured (affected by
              the **range interval** and **downsampling factor**).
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
            The sampling mode changes how the hardware accelerated averaging is done.
            This may either increase SNR or reduce correlation.

            *Mode A* is:

            - optimized for maximal independence of the depth points, giving a higher depth
              resolution than mode B.
            - more suitable for applications like gesture recognition, measuring the distance to a
              movement, and speed measurements.

            *Mode B* is:

            - optimized for maximal SNR per unit time spent on measuring. This makes it more energy
              efficient and suitable for cases where small movements are to be detected over long
              ranges.
            - resulting in roughly 3 dB better SNR per unit time than mode A.
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

        if self.downsampling_factor not in [1, 2, 4, 8]:
            alerts.append(cb.Warning("downsampling_factor", "Must be 1, 2, 4, or 8"))

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


def loads(dump: str, mode=None) -> cb.SensorConfig:
    if mode is None:
        mode = json.loads(dump)["mode"]

    mode = get_mode(mode)
    config = MODE_TO_CONFIG_CLASS_MAP[mode]()
    config._loads(dump)
    return config


load = loads  # for backwards compatibility


def dumps(config: cb.SensorConfig) -> str:
    return config._dumps()
