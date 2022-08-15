# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

import acconeer.exptool as et


def get_sensor_config():
    config = et.a111.IQServiceConfig()
    config.range_interval = [0.3, 0.6]
    config.update_rate = 80
    config.repetition_mode = et.a111.IQServiceConfig.RepetitionMode.SENSOR_DRIVEN
    return config


class Processor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        assert sensor_config.update_rate is not None

        self.f = sensor_config.update_rate
        self.dt = 1 / self.f

        num_hist_points = int(round(self.f * 3))

        self.lp_vel = 0
        self.last_sweep = None
        self.hist_pos = np.zeros(num_hist_points)
        self.sweep_index = 0

    def process(self, data, data_info):
        sweep = data

        n = len(sweep)

        ampl = np.abs(sweep)
        power = np.square(ampl)
        if np.sum(power) > 1e-6:
            com = np.sum(np.arange(n) / n * power) / np.sum(power)  # center of mass
        else:
            com = 0

        if self.sweep_index == 0:
            self.lp_ampl = ampl
            self.lp_com = com
            plot_data = None
        else:
            a = self.alpha(0.1, self.dt)
            self.lp_ampl = a * ampl + (1 - a) * self.lp_ampl
            a = self.alpha(0.25, self.dt)
            self.lp_com = a * com + (1 - a) * self.lp_com

            com_idx = int(self.lp_com * n)
            delta_angle = np.angle(sweep[com_idx] * np.conj(self.last_sweep[com_idx]))
            vel = self.f * 2.5 * delta_angle / (2 * np.pi)

            a = self.alpha(0.1, self.dt)
            self.lp_vel = a * vel + (1 - a) * self.lp_vel

            dp = self.lp_vel / self.f
            self.hist_pos = np.roll(self.hist_pos, -1)
            self.hist_pos[-1] = self.hist_pos[-2] + dp

            hist_len = len(self.hist_pos)
            plot_hist_pos = self.hist_pos - self.hist_pos.mean()
            cut_hist_pos = self.hist_pos[hist_len // 2 :]
            plot_hist_pos_zoom = cut_hist_pos - cut_hist_pos.mean()

            iq_val = np.exp(1j * np.angle(sweep[com_idx])) * self.lp_ampl[com_idx]

            plot_data = {
                "abs": self.lp_ampl,
                "arg": np.angle(sweep),
                "com": self.lp_com,
                "hist_pos": plot_hist_pos,
                "hist_pos_zoom": plot_hist_pos_zoom,
                "iq_val": iq_val,
            }

        self.last_sweep = sweep
        self.sweep_index += 1
        return plot_data

    def alpha(self, tau, dt):
        return 1 - np.exp(-dt / tau)
