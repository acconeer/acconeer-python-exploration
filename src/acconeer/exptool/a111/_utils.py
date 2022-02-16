import numpy as np

from acconeer.exptool.a111._modes import Mode
from acconeer.exptool.structs import configbase


def get_range_depths(sensor_config: configbase.SensorConfig, session_info: dict) -> np.ndarray:
    """Get range depths in meters."""

    range_start = session_info["range_start_m"]
    range_end = range_start + session_info["range_length_m"]

    if sensor_config.mode == Mode.SPARSE:
        num_depths = session_info["data_length"] // sensor_config.sweeps_per_frame
    elif sensor_config.mode == Mode.POWER_BINS:
        num_depths = session_info["bin_count"]
    else:
        num_depths = session_info["data_length"]

    return np.linspace(range_start, range_end, num_depths)
