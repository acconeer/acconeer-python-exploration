# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

import numpy as np
import numpy.typing as npt

from . import channel_convention as ch_conv
from .entities.configs import SensorConfig


def translate_rx_major_frame(
    rx_major_frame: npt.NDArray[np.complex128],
    sensor_config: SensorConfig,
) -> npt.NDArray[np.complex128]:
    take_order = []
    subsweep_offset = 0
    for subsweep_config in sensor_config.subsweeps:
        tx_major_to_rx_major = ch_conv.get_tx_major_to_rx_major_channel_index_table(
            subsweep_config.tx_antenna_mask,
            subsweep_config.rx_antenna_mask,
        )
        for point_idx in range(subsweep_config.num_points):
            point_offset = point_idx * subsweep_config.num_channels

            for tx_major_ch_idx in range(subsweep_config.num_channels):
                rx_major_ch_idx = tx_major_to_rx_major[tx_major_ch_idx]
                take_order.append(subsweep_offset + point_offset + rx_major_ch_idx)

        subsweep_offset += subsweep_config.num_channels * subsweep_config.num_points

    tx_major_frame = rx_major_frame[:, take_order]
    return tx_major_frame
