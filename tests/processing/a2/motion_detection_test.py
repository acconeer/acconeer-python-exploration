# Copyright (c) Acconeer AB, 2026
# All rights reserved
from __future__ import annotations

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.motion_detection import (
    DetectionVolume,
    MotionDetectionConfig,
    MotionDetectionProcessor,
    SensorInstallation,
)
from acconeer.exptool.a2.algo.noise_normalization import load_noise_normalization_recording


def motion_detection_default(record: a2.H5Record) -> MotionDetectionProcessor:
    """Build a :class:`MotionDetectionProcessor` with the default config."""
    noise_normalization_recording = load_noise_normalization_recording(record.file["algo"])
    return MotionDetectionProcessor(
        session_config=record.session_config,
        processor_config=MotionDetectionConfig(antenna_array=a2.AntennaArray.AP212),
        sensor_installation=SensorInstallation(y_rotation=0.0, mount_height_m=1.5),
        detection_volume=DetectionVolume(x_bounds_m=(-4.0, 4.0), y_bounds_m=(0.0, 6.0)),
        noise_norm_recording=noise_normalization_recording,
    )
