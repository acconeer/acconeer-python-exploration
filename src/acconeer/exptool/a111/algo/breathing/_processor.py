# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np
from numpy import pi
from scipy.signal import butter, sosfilt

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.IQServiceConfig()
    config.range_interval = [0.3, 0.8]
    config.update_rate = 80
    config.gain = 0.5
    config.repetition_mode = et.a111.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class ProcessingConfiguration(et.configbase.ProcessingConfig):
    VERSION = 1

    hist_plot_len = et.configbase.FloatParameter(
        label="Plot length",
        unit="s",
        default_value=10,
        limits=(1, 30),
        decimals=0,
    )


class Processor:
    peak_hist_len = 600

    phase_weights_alpha = 0.9
    peak_loc_alpha = 0.95
    sweep_alpha = 0.7
    env_alpha = 0.95

    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        self.config = sensor_config

        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate
        self.hist_plot_len = int(round(processing_config.hist_plot_len * self.f))
        self.breath_hist_len = max(2000, self.hist_plot_len)

        self.peak_history = np.zeros(self.peak_hist_len, dtype="complex")
        self.movement_history = np.zeros(self.peak_hist_len, dtype="float")
        self.breath_history = np.zeros(self.breath_hist_len, dtype="float")
        self.pulse_history = np.zeros(self.hist_plot_len, dtype="float")

        self.breath_sos = np.concatenate(butter(2, 2 * 0.3 / self.f))
        self.breath_zi = np.zeros((1, 2))
        self.pulse_sos = np.concatenate(butter(2, 2 * 5 / self.f))
        self.pulse_zi = np.zeros((1, 2))

        self.last_lp_sweep = None
        self.lp_phase_weights = None
        self.lp_sweep = None
        self.lp_peak_loc = 0

        self.sweep_index = 0

    def process(self, data, data_info):
        sweep = data

        if self.sweep_index == 0:
            self.lp_sweep = np.array(sweep)
            self.lp_env = np.abs(sweep)
            self.lp_peak_loc = np.argmax(self.lp_env)

            out_data = None
        else:
            self.lp_sweep = self.lp(sweep, self.lp_sweep, self.sweep_alpha)
            env = np.abs(self.lp_sweep)
            self.lp_env = self.lp(env, self.lp_env, self.env_alpha)
            peak_loc = np.argmax(self.lp_env)
            self.lp_peak_loc = self.lp(peak_loc, self.lp_peak_loc, self.peak_loc_alpha)

            peak_idx = int(round(self.lp_peak_loc))
            peak = np.mean(self.lp_sweep[peak_idx - 50 : peak_idx + 50])
            self.push(peak, self.peak_history)

            delta = self.lp_sweep * np.conj(self.last_lp_sweep)

            phase_weights = np.imag(delta)
            if self.lp_phase_weights is None:
                self.lp_phase_weights = phase_weights
            else:
                self.lp_phase_weights = self.lp(
                    phase_weights,
                    self.lp_phase_weights,
                    self.phase_weights_alpha,
                )

            weights = np.abs(self.lp_phase_weights) * env

            delta_dist = np.dot(weights, np.angle(delta))
            delta_dist *= 2.5 / (2.0 * pi * sum(weights + 0.00001))

            y = self.movement_history[0] + delta_dist
            self.push(y, self.movement_history)

            y_breath, self.breath_zi = sosfilt(self.breath_sos, np.array([y]), zi=self.breath_zi)
            self.push(y_breath, self.breath_history)

            y_pulse, self.pulse_zi = sosfilt(self.pulse_sos, np.array([y]), zi=self.pulse_zi)
            self.push(y_pulse, self.pulse_history)

            maxs = self.find_peaks(self.breath_history, 100)
            mins = self.find_peaks(-self.breath_history, 100)
            max_idx = 0
            min_idx = 0
            inhale_time = None
            exhale_time = None
            inhale_dist = 0
            exhale_dist = 0
            exhale = None
            first_peak = None
            while not (inhale_time and exhale_time):
                if not (min_idx < mins.shape[0] and max_idx < maxs.shape[0]):
                    break

                if maxs[max_idx, 0] < mins[min_idx, 0]:
                    exhale_dist = mins[min_idx, 1] + maxs[max_idx, 1]
                    if exhale_dist > 1 and exhale_dist < 20:
                        exhale_time = mins[min_idx, 0] - maxs[max_idx, 0]
                        if first_peak is None:
                            first_peak = maxs[max_idx, 0]
                        exhale = True
                    max_idx += 1
                else:
                    inhale_dist = mins[min_idx, 1] + maxs[max_idx, 1]
                    if inhale_dist > 1 and inhale_dist < 20:
                        inhale_time = maxs[max_idx, 0] - mins[min_idx, 0]
                        exhale = False
                        if first_peak is None:
                            first_peak = mins[min_idx, 0]
                    min_idx += 1

            breathing = False
            if inhale_time is not None and exhale_time is not None:
                bpm = 60.0 / ((inhale_time + exhale_time) / self.f)
                symmetry = (inhale_dist - exhale_dist) / (inhale_dist + exhale_dist)
                first_peak_rel = first_peak / (inhale_time + exhale_time)
                if 3 < bpm < 30 and abs(symmetry) < 0.6 and first_peak_rel < 0.7:
                    breathing = True

            if breathing:
                bstr = "Exhaling" if exhale else "Inhaling"
                bpm_text = "{}, BPM {:0.1f}, depth {:0.1f} mm".format(bstr, bpm, inhale_dist)
            else:
                bpm_text = None

            # Make an explicit copy, otherwise flip will not return a new object
            breath_hist_plot = self.breath_history[: self.hist_plot_len]
            breath_hist_plot = np.array(np.flip(breath_hist_plot, axis=0))
            breath_hist_plot -= (np.max(breath_hist_plot) + np.min(breath_hist_plot)) * 0.5

            zoom_hist_plot = self.pulse_history[: self.hist_plot_len // 2]
            zoom_hist_plot = np.array(np.flip(zoom_hist_plot, axis=0))
            zoom_hist_plot -= (max(zoom_hist_plot) + min(zoom_hist_plot)) * 0.5

            out_data = {
                "peak_hist": self.peak_history[:100],
                "peak_std_mm": 2.5 * np.std(np.unwrap(np.angle(self.peak_history))) / (2.0 * pi),
                "env_ampl": abs(self.lp_sweep),
                "env_delta": self.lp_phase_weights,
                "peak_idx": peak_idx,
                "breathing_history": breath_hist_plot,
                "breathing_text": bpm_text,
                "zoom_hist": zoom_hist_plot,
            }

        self.last_lp_sweep = self.lp_sweep
        self.sweep_index += 1
        return out_data

    def lp(self, new, state, alpha):
        return alpha * state + (1 - alpha) * new

    def push(self, val, arr):
        res = np.empty_like(arr)
        res[0] = val
        res[1:] = arr[:-1]
        arr[...] = res

    def find_peaks(self, env, width):
        n = len(env)
        peaks = np.zeros((0, 2))
        for idx in range(0, n, width):
            mi = np.argmax(env[idx : min(idx + width, n)]) + idx
            mi2 = np.argmax(env[max(mi - width, 0) : min(mi + width, n)])
            mi2 += max(mi - width, 0)
            if mi == mi2 and (0 < mi < n - 1):
                peaks = np.concatenate((peaks, np.array([[mi, env[mi]]])), axis=0)
        return peaks
