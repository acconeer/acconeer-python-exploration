from typing import Tuple

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a121._core import SensorConfig


def approx_distances_m(config: SensorConfig) -> Tuple[npt.NDArray[np.float_], float]:
    points = np.arange(config.num_points) * config.step_length + config.start_point
    distances = points * 2.5e-3
    step_length_m = config.step_length * 2.5e-3
    return distances, step_length_m
