from typing import Tuple

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import SensorConfig


def approx_distances_m(config: SensorConfig) -> Tuple[npt.NDArray[np.float_], float]:
    points = np.arange(config.num_points) * config.step_length + config.start_point
    distances = points * 2.5e-3
    step_length_m = config.step_length * 2.5e-3
    return distances, step_length_m


def approx_sweep_rate(config: SensorConfig) -> float:
    ppp = {1: 24, 2: 20, 3: 16, 4: 16, 5: 16}[config.profile.value]

    n = 3 * ppp + config.num_points * config.hwaas * ppp

    return config.prf.frequency / n


def approx_fft_vels(config: SensorConfig) -> Tuple[npt.NDArray, float]:
    sweep_rate = approx_sweep_rate(config)
    if config.sweep_rate is not None:
        sweep_rate = min([sweep_rate, config.sweep_rate])

    spf = config.sweeps_per_frame
    f_res = 1 / spf
    freqs = np.fft.fftshift(np.fft.fftfreq(spf))  # type: ignore[call-overload]
    f_to_v = 2.5e-3 * sweep_rate
    return freqs * f_to_v, f_res * f_to_v
