# Copyright (c) Acconeer AB, 2026
# All rights reserved

import pytest

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import PERCEIVED_WAVELENGTH
from acconeer.exptool.a121.algo.obstacle import Processor, ProcessorConfig, ProcessorContext


def test_processor_dv_matches_fft_velocity_resolution() -> None:
    sweeps_per_frame = 32
    sweep_rate = 1000.0
    sensor_config = a121.SensorConfig(
        sweeps_per_frame=sweeps_per_frame,
        sweep_rate=sweep_rate,
        subsweeps=[a121.SubsweepConfig(start_point=40, num_points=10, step_length=4)],
    )
    processor = Processor(
        sensor_config=sensor_config,
        processor_config=ProcessorConfig(),
        context=ProcessorContext(update_rate=10.0),
    )

    # One FFT bin is sweep_rate / sweeps_per_frame Hz of Doppler, and
    # PERCEIVED_WAVELENGTH already holds lambda / 2.
    expected_dv = PERCEIVED_WAVELENGTH * sweep_rate / sweeps_per_frame

    assert processor.dv == pytest.approx(expected_dv)
    assert processor.dv == pytest.approx(processor.subsweep_processors[0].dv)
