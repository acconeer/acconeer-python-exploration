# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Tuple

import numpy as np
import numpy.typing as npt

from acconeer.exptool import a121


def get_distances_m(
    config: a121.SensorConfig,
    metadata: a121.Metadata,
) -> Tuple[npt.NDArray[np.float_], float]:
    points = np.arange(config.num_points) * config.step_length + config.start_point
    distances_m = points * metadata.base_step_length_m
    step_length_m = config.step_length * metadata.base_step_length_m
    return distances_m, step_length_m


def get_approx_sweep_rate(config: a121.SensorConfig) -> float:
    ppp = {1: 24, 2: 20, 3: 16, 4: 16, 5: 16}[config.profile.value]

    n = 3 * ppp + config.num_points * config.hwaas * ppp

    return config.prf.frequency / n


def get_approx_fft_vels(config: a121.SensorConfig) -> Tuple[npt.NDArray, float]:
    sweep_rate = get_approx_sweep_rate(config)
    if config.sweep_rate is not None:
        sweep_rate = min([sweep_rate, config.sweep_rate])

    spf = config.sweeps_per_frame
    f_res = 1 / spf
    freqs = np.fft.fftshift(np.fft.fftfreq(spf))  # type: ignore[call-overload]
    f_to_v = 2.5e-3 * sweep_rate
    return freqs * f_to_v, f_res * f_to_v
