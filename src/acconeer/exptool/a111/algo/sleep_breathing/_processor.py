# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np
from scipy import signal

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.IQServiceConfig()
    config.range_interval = [0.4, 0.8]
    config.update_rate = 60
    config.gain = 0.6
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    n_dft = et.configbase.FloatParameter(
        label="Estimation window",
        unit="s",
        default_value=15,
        limits=(2, 20),
        updateable=False,
        order=0,
    )

    t_freq_est = et.configbase.FloatParameter(
        label="Time between estimation",
        unit="s",
        default_value=0.2,
        limits=(0.1, 10),
        updateable=False,
        order=10,
    )

    D = et.configbase.IntParameter(
        label="Distance downsampling",
        default_value=124,
        limits=(0, 248),
        updateable=False,
        order=20,
    )

    f_high = et.configbase.FloatParameter(
        label="Bandpass high freq",
        unit="Hz",
        default_value=0.8,
        limits=(0, 10),
        updateable=False,
        order=30,
    )

    f_low = et.configbase.FloatParameter(
        label="Bandpass low freq",
        unit="Hz",
        default_value=0.2,
        limits=(0, 10),
        updateable=False,
        order=40,
    )

    lambda_p = et.configbase.FloatParameter(
        label="Threshold: Peak to noise ratio",
        default_value=40,
        limits=(1, 1000),
        updateable=False,
        order=50,
    )

    lambda_05 = et.configbase.FloatParameter(
        label="Threshold: Peak to half harmonic ratio",
        default_value=1,
        limits=(0, 10),
        updateable=False,
        order=60,
    )


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.config = sensor_config

        # Settings
        # Data length for frequency estimation [s] | 20
        n_dft = processing_config.n_dft
        # Time between frequency estimations [s] | 2
        t_freq_est = processing_config.t_freq_est
        # Time constant low-pass filter on IQ-data [s] | 0.04
        tau_iq = 0.04
        # Time constant low-pass filter on IQ-data [s] | 150
        self.f_s = self.config.update_rate
        # Spatial or Range down sampling factor | 124
        self.D = processing_config.D
        # Lowest frequency of interest [Hz] | 0.1
        self.f_low = processing_config.f_low
        # Highest frequency of interest [Hz] | 1
        self.f_high = processing_config.f_high
        # Time down sampling for DFT | 40 f_s/M ~ 10 Hz
        self.M = int(self.f_s / 10)
        # Threshold: spectral peak to noise ratio [1] | 50
        self.lambda_p = processing_config.lambda_p
        # Threshold: ratio fundamental and half harmonic
        self.lambda_05 = processing_config.lambda_05
        # Interpolation between DFT points
        self.interpolate = True

        self.delta_f = 1 / n_dft
        self.dft_f_vec = np.arange(self.f_low, self.f_high, self.delta_f)
        self.dft_points = np.size(self.dft_f_vec)

        # Butterworth bandpass filter
        f_n = self.f_s / 2
        v_low = self.f_low / f_n
        v_high = self.f_high / f_n
        self.b, self.a = signal.butter(4, [v_low, v_high], btype="bandpass")

        # Exponential lowpass filter
        self.alpha_iq = np.exp(-2 / (self.f_s * tau_iq))
        self.alpha_phi = np.exp(-2 * self.f_low / self.f_s)

        # Parameter init
        self.sweeps_in_block = int(np.ceil(n_dft * self.f_s))
        self.new_sweeps_per_results = int(np.ceil(t_freq_est * self.f_s))
        self.phi_vec = np.zeros((self.sweeps_in_block, 1))
        self.f_est_vec = np.zeros(1)
        self.f_dft_est_vec = np.zeros(1)
        self.snr_vec = 0

        self.sweep_index = 0

    def process(self, data, data_info):
        sweep = data

        if self.sweep_index == 0:
            delay_points = int(np.ceil(np.size(sweep) / self.D))
            self.data_s_d_mat = np.zeros((self.sweeps_in_block, delay_points), dtype="complex")
            self.data_s_d_mat[self.sweep_index, :] = self.downsample(sweep, self.D)

            out_data = None
        elif self.sweep_index < self.sweeps_in_block:
            self.data_s_d_mat[self.sweep_index, :] = self.iq_lp_filter_time(
                self.data_s_d_mat[self.sweep_index - 1, :], self.downsample(sweep, self.D)
            )

            temp_phi = self.unwrap_phase(
                self.phi_vec[self.sweep_index - 1],
                self.data_s_d_mat[self.sweep_index, :],
                self.data_s_d_mat[self.sweep_index - 1, :],
            )

            self.phi_vec[self.sweep_index] = self.unwrap_phase(
                self.phi_vec[self.sweep_index - 1],
                self.data_s_d_mat[self.sweep_index, :],
                self.data_s_d_mat[self.sweep_index - 1, :],
            )

            phi_filt = signal.lfilter(self.b, self.a, self.phi_vec, axis=0)

            out_data = {
                "phi_raw": self.phi_vec,
                "phi_filt": phi_filt,
                "power_spectrum": np.zeros(self.dft_points),
                "x_dft": np.linspace(self.f_low, self.f_high, self.dft_points),
                "f_dft_est_hist": self.f_dft_est_vec,
                "f_est_hist": self.f_est_vec,
                "f_dft_est": 0,
                "f_est": 0,
                "f_low": self.f_low,
                "f_high": self.f_high,
                "snr": 0,
                "lambda_p": self.lambda_p,
                "lambda_05": self.lambda_05,
                "dist_range": self.config.range_interval,
                "init_progress": round(100 * self.sweep_index / self.sweeps_in_block),
            }
        else:
            # Lowpass filter IQ data downsampled in distance points
            self.data_s_d_mat = np.roll(self.data_s_d_mat, -1, axis=0)
            self.data_s_d_mat[-1, :] = self.iq_lp_filter_time(
                self.data_s_d_mat[-2, :], self.downsample(sweep, self.D)
            )

            # Phase unwrapping of IQ data
            temp_phi = self.unwrap_phase(
                self.phi_vec[-1], self.data_s_d_mat[-1, :], self.data_s_d_mat[-2, :]
            )
            self.phi_vec = np.roll(self.phi_vec, -1, axis=0)
            self.phi_vec[-1] = temp_phi

            if np.mod(self.sweep_index, self.new_sweeps_per_results - 1) == 0:
                # Bandpass filter unwrapped data
                phi_filt_vec = signal.lfilter(self.b, self.a, self.phi_vec, axis=0)
                P, dft_est, _ = self.dft(self.downsample(phi_filt_vec, self.M))
                f_breath_est, _, snr, _ = self.breath_freq_est(P)

                self.f_est_vec = np.append(self.f_est_vec, f_breath_est)
                self.f_dft_est_vec = np.append(self.f_dft_est_vec, dft_est)
                self.snr_vec = np.append(self.snr_vec, snr)

                out_data = {
                    "phi_raw": self.phi_vec,
                    "phi_filt": phi_filt_vec,
                    "power_spectrum": P,
                    "x_dft": np.linspace(self.f_low, self.f_high, self.dft_points),
                    "f_dft_est_hist": self.f_dft_est_vec,
                    "f_est_hist": self.f_est_vec,
                    "f_dft_est": dft_est,
                    "f_est": f_breath_est,
                    "f_low": self.f_low,
                    "f_high": self.f_high,
                    "snr": snr,
                    "lambda_p": self.lambda_p,
                    "lambda_05": self.lambda_05,
                    "dist_range": self.config.range_interval,
                    "init_progress": None,
                }
            else:
                out_data = None

        self.sweep_index += 1
        return out_data

    def downsample(self, data, n):
        return data[::n]

    def iq_lp_filter_time(self, state, new_data):
        return self.alpha_iq * state + (1 - self.alpha_iq) * new_data

    def unwrap_phase(self, phase_lp, data_1, data_2):
        return phase_lp * self.alpha_phi + np.angle(np.mean(data_2 * np.conjugate(data_1)))

    def dft(self, data):
        data = np.squeeze(data)
        n_vec = np.arange(data.size) * self.M
        dft = np.exp((2j * np.pi / self.f_s) * np.outer(self.dft_f_vec, n_vec))
        P = np.square(np.abs(np.matmul(dft, data)))
        idx_f = np.argmax(P)
        dft_est = self.dft_f_vec[idx_f]
        return P, dft_est, P[idx_f]

    def noise_est(self, P):
        return np.mean(np.sort(P)[: (self.dft_points // 2) - 1])

    def half_peak_frequency(self, P, f_est):
        idx_half = int(f_est / (2 * self.delta_f))
        if idx_half < self.f_low:
            return 0
        else:
            return (1 / self.delta_f) * (
                (self.dft_f_vec[idx_half + 1] - f_est / 2) * P[idx_half]
                + (f_est / 2 - self.dft_f_vec[idx_half]) * P[idx_half + 1]
            )

    def breath_freq_est(self, P):
        f_idx = np.argmax(P)
        P_peak = P[f_idx]

        if self.interpolate:
            f_est, P_peak = self.freq_quad_interpolation(P)
        else:
            f_est = self.dft_f_vec[f_idx]

        P_half = self.half_peak_frequency(P, f_est)

        if P_peak < self.lambda_05 * P_half:
            f_est = f_est / 2
            P_peak = P_half

        if self.f_low < f_est < self.f_high and P_peak > self.lambda_p * self.noise_est(P):
            f_est_valid = True
        else:
            f_est_valid = False
            f_est = 0

        snr = P_peak / self.noise_est(P)
        return f_est, P_peak, snr, f_est_valid

    def freq_quad_interpolation(self, P):
        f_idx = np.argmax(P)

        if 0 < f_idx < (P.size - 1) and P.size > 3:
            f_est = self.dft_f_vec[f_idx] + self.delta_f / 2 * (
                (np.log(P[f_idx + 1]) - np.log(P[f_idx - 1]))
                / (2 * np.log(P[f_idx]) - np.log(P[f_idx + 1]) - np.log(P[f_idx - 1]))
            )
            P_peak = P[f_idx] + np.exp(
                (1 / 8)
                * np.square(np.log(P[f_idx + 1]) - np.log(P[f_idx - 1]))
                / (2 * np.log(P[f_idx]) - np.log(P[f_idx + 1]) - np.log(P[f_idx - 1]))
            )

            if not (self.f_low < f_est < self.f_high):
                f_est = 0
        else:
            f_est = 0
            P_peak = 0

        return f_est, P_peak
