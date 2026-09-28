# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import attrs
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool import a2
from acconeer.exptool import type_migration as tm
from acconeer.exptool.a2.algo.heatmap import config_legacy
from acconeer.exptool.a2.algo.heatmap.config_common import (
    HeatmapAndSessionConfigCommon,
    HeatmapConfigCommon,
)


@attributes_doc
@attrs.mutable
class HeatmapConfig(HeatmapConfigCommon):
    covariance_matrix_time_constant_s: float
    """Time constant for exponential smoothing of the covariance matrices"""

    high_pass_filter_time_constant_s: float
    """Time constant for the high-pass filter."""

    steering_vector_epsilon: float
    """Steering vector epsilon for uncertainty in position."""

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            covariance_matrix_time_constant_s=0.5,
            high_pass_filter_time_constant_s=1.5,
            steering_vector_epsilon=0.2,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=80,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
        )


@attrs.mutable
class HeatmapAndSessionConfig(HeatmapAndSessionConfigCommon[HeatmapConfig]):
    @classmethod
    def default(cls) -> te.Self:
        return cls(
            heatmap_config=HeatmapConfig.default(),
            session_config=a2.SessionConfig.default(),
        )


@attrs.mutable
class HeatmapConfig_v1(HeatmapConfigCommon):
    covariance_matrix_time_constant_s: float
    high_pass_filter_time_constant_s: float
    steering_vector_epsilon: float
    normalized_heat_cutoff: float = attrs.field(default=0.75)
    max_2d_heat: int | None = attrs.field(default=None)
    log_scale_output: bool = attrs.field(default=False)

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            covariance_matrix_time_constant_s=0.5,
            high_pass_filter_time_constant_s=1.5,
            steering_vector_epsilon=0.2,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=80,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
        )

    def migrate(self) -> HeatmapConfig:
        return HeatmapConfig(
            az_angle_range=self.az_angle_range,
            el_angle_range=self.el_angle_range,
            num_az_angles=self.num_az_angles,
            num_el_angles=self.num_el_angles,
            antenna_array=self.antenna_array,
            covariance_matrix_time_constant_s=self.covariance_matrix_time_constant_s,
            high_pass_filter_time_constant_s=self.high_pass_filter_time_constant_s,
            steering_vector_epsilon=self.steering_vector_epsilon,
            # normalized_heat_cutoff, max_2d_heat, log_scale_output moved to HeatmapPlotConfig
        )


def migrate_legacy(old: config_legacy.HeatmapConfigLegacy) -> HeatmapConfig_v1:
    return HeatmapConfig_v1(
        antenna_array=a2.AntennaArray.AP212,
        covariance_matrix_time_constant_s=0.5,
        high_pass_filter_time_constant_s=1.5,
        steering_vector_epsilon=0.2,
        az_angle_range=old.az_angle_range,
        el_angle_range=old.el_angle_range,
        num_az_angles=old.num_az_angles,
        num_el_angles=old.num_el_angles,
    )


heatmap_config_timeline = (
    config_legacy.heatmap_config_timeline.epoch(
        HeatmapConfig_v1,
        migrate_legacy,
        fail=[],
    )
    .load(str, HeatmapConfig_v1.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(HeatmapConfig, HeatmapConfig_v1.migrate, fail=[])
    .load(str, HeatmapConfig.from_json, fail=tm.common_exceptions.FROM_JSON)
)
