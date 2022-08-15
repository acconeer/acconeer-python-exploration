# Copyright (c) Acconeer AB, 2022
# All rights reserved

from enum import Enum

import numpy as np
from scipy.signal.windows import hann

import acconeer.exptool as et

from .constants import EST_VEL_HISTORY_LENGTH, HALF_WAVELENGTH, HISTORY_LENGTH, NUM_SAVED_SEQUENCES


SD_HISTORY_LENGTH = HISTORY_LENGTH  # s
SEQUENCE_TIMEOUT_LENGTH = 0.5  # s


def get_sensor_config():
    config = et.a111.SparseServiceConfig()
    config.profile = et.a111.SparseServiceConfig.Profile.PROFILE_4
    config.sampling_mode = et.a111.SparseServiceConfig.SamplingMode.A
    config.range_interval = [0.36, 0.60]
    config.downsampling_factor = 4
    config.sweeps_per_frame = 512
    config.hw_accelerated_average_samples = 60
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 6

    class SpeedUnit(Enum):
        METER_PER_SECOND = ("m/s", 1)
        KILOMETERS_PER_HOUR = ("km/h", 3.6)
        MILES_PER_HOUR = ("mph", 2.237)

        @property
        def label(self):
            return self.value[0]

        @property
        def scale(self):
            return self.value[1]

    class ProcessingMethod(Enum):
        WELCH = "Welch"
        BARTLETT = "Bartlett"

    threshold = et.configbase.FloatParameter(
        label="Threshold",
        default_value=4.0,
        limits=(1, 100),
        decimals=2,
        updateable=True,
        logscale=True,
        order=0,
        help=(
            "The threshold parameter determines how great PSD "
            "a point needs to have to be included in the speed estimation. "
            "The threshold value is converted to dB when displayed in the *Normalized PSD-graph*"
        ),
    )

    min_speed = et.configbase.FloatParameter(
        label="Minimum speed",
        unit="m/s",
        default_value=0.5,
        limits=(0, 5),
        decimals=1,
        updateable=True,
        order=10,
        help=("The minimum speed to be displayed."),
    )

    fft_oversampling_factor = et.configbase.IntParameter(
        label="FFT oversampling factor",
        default_value=1,
        valid_values=[1, 2, 4, 8],
        updateable=False,
        order=11,
    )

    processing_method = et.configbase.EnumParameter(
        label="Processing method",
        default_value=ProcessingMethod.WELCH,
        enum=ProcessingMethod,
        updateable=False,
        help=(
            "In Welch's method the segments overlap 50% and the periodograms are "
            "windowed using a Hann window."
            "\nIn Bartlett's method there is no overlap between segments "
            "and the periodograms are not modified."
            "\nWelch's method will result in lower variance and added complexity"
            "compared to Bartlett's method."
        ),
        order=12,
    )

    num_segments = et.configbase.IntParameter(
        label="Number of segments",
        default_value=3,
        limits=(1, None),
        updateable=False,
        help=("Number of segments used in Welch's/Bartlett's method."),
        order=13,
    )

    shown_speed_unit = et.configbase.EnumParameter(
        label="Speed unit",
        default_value=SpeedUnit.METER_PER_SECOND,
        enum=SpeedUnit,
        updateable=True,
        order=100,
    )

    show_data_plot = et.configbase.BoolParameter(
        label="Show data",
        default_value=False,
        updateable=True,
        order=110,
    )

    show_sd_plot = et.configbase.BoolParameter(
        label="Show spectral density",
        default_value=True,
        updateable=True,
        order=120,
    )

    show_vel_history_plot = et.configbase.BoolParameter(
        label="Show speed history",
        default_value=True,
        updateable=True,
        order=130,
    )

    num_shown_sequences = et.configbase.IntParameter(
        label="Number of history bars",
        default_value=10,
        limits=(1, NUM_SAVED_SEQUENCES),
        updateable=True,
        order=150,
        help=("Number of bars to be displayed in the bar graph"),
    )

    def check(self):
        alerts = []

        if self.processing_method == self.ProcessingMethod.WELCH and self.num_segments % 2 != 1:
            alerts.append(et.configbase.Error("num_segments", "Number of segments must be odd"))

        if self.processing_method == self.ProcessingMethod.BARTLETT and self.num_segments % 2 != 0:
            alerts.append(et.configbase.Error("num_segments", "Number of segments must be even"))

        return alerts

    def check_sensor_config(self, sensor_config):
        alerts = {
            "processing": [],
            "sensor": [],
        }

        if self.processing_method == ProcessingConfiguration.ProcessingMethod.WELCH:
            # Overlap is 50% of the segment size
            segment_length = 2 * sensor_config.sweeps_per_frame // (self.num_segments + 1)
        else:
            segment_length = sensor_config.sweeps_per_frame // self.num_segments

        if 0 <= segment_length < 8:
            alerts["processing"].append(
                et.configbase.Error(
                    "num_segments",
                    (
                        "Number of points in segment is too small."
                        "\nDecrease number of segments"
                        "\nor increase number of sweeps per frame"
                    ),
                )
            )

        if (sensor_config.sweeps_per_frame & (sensor_config.sweeps_per_frame - 1)) != 0:
            lower = 2 ** int(np.floor(np.log2(sensor_config.sweeps_per_frame)))
            upper = 2 ** int(np.ceil(np.log2(sensor_config.sweeps_per_frame)))
            alerts["sensor"].append(
                et.configbase.Error(
                    "sweeps_per_frame",
                    (
                        "Must have a value that is a power of 2."
                        "\nClosest values are {} and {}".format(lower, upper)
                    ),
                )
            )

        return alerts


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.sweeps_per_frame = sensor_config.sweeps_per_frame
        sweep_rate = session_info["sweep_rate"]
        est_frame_rate = sweep_rate / self.sweeps_per_frame
        self.depths = et.a111.get_range_depths(sensor_config, session_info)

        if processing_config.processing_method == ProcessingConfiguration.ProcessingMethod.WELCH:
            segment_length = 2 * self.sweeps_per_frame // (processing_config.num_segments + 1)
        else:
            segment_length = self.sweeps_per_frame // processing_config.num_segments

        self.fft_length = segment_length * processing_config.fft_oversampling_factor
        self.num_noise_est_bins = 3
        noise_est_tc = 1.0

        self.sequence_timeout_count = int(round(est_frame_rate * SEQUENCE_TIMEOUT_LENGTH))
        est_vel_history_size = int(round(est_frame_rate * EST_VEL_HISTORY_LENGTH))
        sd_history_size = int(round(est_frame_rate * SD_HISTORY_LENGTH))
        self.noise_est_sf = self.tc_to_sf(noise_est_tc, est_frame_rate)
        self.bin_fs = np.fft.rfftfreq(self.fft_length) * sweep_rate
        self.bin_vs = self.bin_fs * HALF_WAVELENGTH

        num_bins = self.bin_fs.size
        self.nasd_history = np.zeros([sd_history_size, num_bins])
        self.est_vel_history = np.full(est_vel_history_size, np.nan)
        self.belongs_to_last_sequence = np.zeros(est_vel_history_size, dtype=bool)
        self.noise_est = 0
        self.current_sequence_idle = self.sequence_timeout_count + 1
        self.sequence_vels = np.zeros(NUM_SAVED_SEQUENCES)
        self.update_idx = 0

        self.num_segments = processing_config.num_segments
        self.processing_method = processing_config.processing_method

        self.update_processing_config(processing_config)

    def update_processing_config(self, processing_config):
        self.min_speed = processing_config.min_speed
        self.threshold = processing_config.threshold

    def tc_to_sf(self, tc, fs):
        if tc <= 0.0:
            return 0.0

        return np.exp(-1.0 / (tc * fs))

    def dynamic_sf(self, static_sf):
        return min(static_sf, 1.0 - 1.0 / (1.0 + self.update_idx))

    def process(self, data, data_info):
        frame = data

        # Basic speed estimate using Welch's method

        zero_mean_frame = frame - frame.mean(axis=0, keepdims=True)
        psd_length = self.fft_length // 2 + 1

        if self.processing_method == ProcessingConfiguration.ProcessingMethod.WELCH:
            # Overlap is 50% of the segment size
            segment_length = 2 * self.sweeps_per_frame // (self.num_segments + 1)
        else:
            segment_length = self.sweeps_per_frame // self.num_segments

        window = hann(segment_length, sym=False)
        window_norm = np.sum(window**2)

        fft_segments = np.empty((self.num_segments, psd_length, len(self.depths)))

        for i in range(self.num_segments):
            if self.processing_method == ProcessingConfiguration.ProcessingMethod.WELCH:
                offset_segment = i * segment_length // 2
            else:
                offset_segment = i * segment_length

            current_segment = zero_mean_frame[offset_segment : offset_segment + segment_length]

            if self.processing_method == ProcessingConfiguration.ProcessingMethod.WELCH:
                current_segment = current_segment * window[:, None]

            fft_segments[i] = (
                np.square(
                    np.abs(
                        np.fft.rfft(
                            current_segment,
                            self.fft_length,
                            axis=0,
                        )
                    )
                )
                / window_norm
            )  # rfft automatically pads if n<nfft

        # Add FFTs of different segments and average to decrease FFT variance

        psds = np.mean(fft_segments, axis=0)

        psds[1 : psd_length - 1] *= 2  # Double frequencies except DC and Nyquist

        psd = np.max(psds, axis=1)  # Power Spectral Density
        asd = np.sqrt(psd)  # Amplitude Spectral Density

        inst_noise_est = np.mean(asd[(-self.num_noise_est_bins - 1) : -1])
        sf = self.dynamic_sf(self.noise_est_sf)  # Smoothing factor
        self.noise_est = sf * self.noise_est + (1.0 - sf) * inst_noise_est

        nasd = asd / self.noise_est  # Normalized Amplitude Spectral Density

        over = nasd > self.threshold
        est_idx = np.where(over)[0][-1] if np.any(over) else np.nan

        if est_idx > 0:  # evaluates to false if nan
            est_vel = self.bin_vs[est_idx]
        else:
            est_vel = np.nan

        if est_vel < self.min_speed:  # evaluates to false if nan
            est_vel = np.nan

        # Sequence

        self.belongs_to_last_sequence = np.roll(self.belongs_to_last_sequence, -1)

        if np.isnan(est_vel):
            self.current_sequence_idle += 1
        else:
            if self.current_sequence_idle > self.sequence_timeout_count:
                self.sequence_vels = np.roll(self.sequence_vels, -1)
                self.sequence_vels[-1] = est_vel
                self.belongs_to_last_sequence[:] = False

            self.current_sequence_idle = 0
            self.belongs_to_last_sequence[-1] = True

            if est_vel > self.sequence_vels[-1]:
                self.sequence_vels[-1] = est_vel

        # Data for plots

        self.est_vel_history = np.roll(self.est_vel_history, -1, axis=0)
        self.est_vel_history[-1] = est_vel

        if np.all(np.isnan(self.est_vel_history)):
            output_vel = None
        else:
            output_vel = np.nanmax(self.est_vel_history)

        self.nasd_history = np.roll(self.nasd_history, -1, axis=0)
        self.nasd_history[-1] = nasd

        nasd_temporal_max = np.max(self.nasd_history, axis=0)

        temporal_max_threshold = self.threshold

        self.update_idx += 1

        return {
            "frame": frame,
            "nasd": nasd,
            "nasd_temporal_max": nasd_temporal_max,
            "temporal_max_threshold": temporal_max_threshold,
            "vel_history": self.est_vel_history,
            "vel": output_vel,
            "sequence_vels": self.sequence_vels,
            "belongs_to_last_sequence": self.belongs_to_last_sequence,
        }
