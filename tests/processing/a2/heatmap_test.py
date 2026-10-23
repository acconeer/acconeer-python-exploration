# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved
from __future__ import annotations

from typing import Tuple

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap import conventional
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationResultProcessor,
    load_noise_normalization_recording,
)


def conventional_heatmap_processing(
    record: a2.H5Record,
) -> Tuple[
    conventional.HeatmapProcessor, NoiseNormalizationResultProcessor, conventional.HeatmapConfig
]:
    ss = record.session_config.sensor_config.subsweep
    algo_group = record.require_algo_group("conventional_heatmap")
    heatmap_config_json_str = bytes.decode(algo_group["plugin_config"][()])
    heatmap_config = conventional.heatmap_config_timeline.migrate(heatmap_config_json_str)

    max_update_rate = float(algo_group["max_update_rate"][()])

    noise_normalization_recording = load_noise_normalization_recording(algo_group)
    assert noise_normalization_recording is not None
    noise_normalization_processor = NoiseNormalizationResultProcessor(
        record.session_config,
        noise_normalization_recording,
    )

    if record.session_config.update_rate is None:
        update_rate = max_update_rate
    else:
        update_rate = min(
            max_update_rate,
            record.session_config.update_rate,
        )

    return (
        conventional.HeatmapProcessor(ss, heatmap_config, update_rate),
        noise_normalization_processor,
        heatmap_config,
    )
