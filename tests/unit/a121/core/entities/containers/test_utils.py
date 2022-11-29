# Copyright (c) Acconeer AB, 2022
# All rights reserved

import numpy as np

from acconeer.exptool.a121._core.entities.containers import Metadata, utils


def test_get_subsweeps_from_frame() -> None:
    metadata = Metadata(
        frame_data_length=8,
        sweep_data_length=4,
        subsweep_data_length=np.array([2, 2]),
        subsweep_data_offset=np.array([0, 2]),
        calibration_temperature=0,
        tick_period=0,
        base_step_length_m=0,
        max_sweep_rate=0,
    )
    input_array = np.array(
        [
            [1, 2, 3, 4],
            [5, 6, 7, 8],
        ]
    )
    expected = [
        np.array(
            [
                [1, 2],
                [5, 6],
            ]
        ),
        np.array(
            [
                [3, 4],
                [7, 8],
            ]
        ),
    ]

    np.testing.assert_array_equal(utils.get_subsweeps_from_frame(input_array, metadata), expected)
