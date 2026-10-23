# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import typing as t
from enum import Enum, auto

import attrs
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool import a2
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool.a2.algo._utils import HEATMAP_FALLBACK_UPDATE_RATE, sf_to_tc
from acconeer.exptool.a2.algo.heatmap import config_legacy
from acconeer.exptool.a2.algo.heatmap.config_common import (
    HeatmapAndSessionConfigCommon,
    HeatmapConfigCommon,
)


@attributes_doc
@attrs.mutable
class HeatmapConfig(HeatmapConfigCommon):
    class HeatmapMode(Enum):
        """Heatmap mode. ``MOVEMENT`` high-pass filters data. ``DISTANCE`` does no filtering"""

        DISTANCE = auto()
        MOVEMENT = auto()

        @classmethod
        def _missing_(cls, value: object) -> t.Optional[te.Self]:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    heatmap_mode: HeatmapMode = attrs.field(converter=HeatmapMode)
    """Heatmap mode to use"""

    covariance_matrix_time_constant_s: float
    """Time constant for exponential smoothing of the covariance matrices"""

    high_pass_filter_time_constant_s: float
    """Time constant for the high-pass filter."""

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=cls.HeatmapMode.DISTANCE,
            covariance_matrix_time_constant_s=0.5,
            high_pass_filter_time_constant_s=1.5,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=30,
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


@attributes_doc
@attrs.mutable
class HeatmapConfig_v0(HeatmapConfigCommon):
    heatmap_mode: HeatmapConfig.HeatmapMode = attrs.field(converter=HeatmapConfig.HeatmapMode)
    """Heatmap mode to use"""

    covariance_matrix_smoothing_factor: float
    """Exponential smoothing factor of the covariance matrices"""

    high_pass_filter_smoothing_factor: float
    """Exponential smoothing factor of the high-pass filter"""

    update_count: int
    """The number of Results the heatmap processor is fed before getting a heatmap"""

    normalized_heat_cutoff: float = attrs.field(default=0.75)
    max_2d_heat: t.Optional[int] = attrs.field(default=None)
    log_scale_output: bool = attrs.field(default=False)

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=HeatmapConfig.HeatmapMode.DISTANCE,
            covariance_matrix_smoothing_factor=0.95,
            high_pass_filter_smoothing_factor=0.99,
            update_count=5,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=23,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
        )

    def migrate(self) -> HeatmapConfig_v1:
        return HeatmapConfig_v1(
            az_angle_range=self.az_angle_range,
            el_angle_range=self.el_angle_range,
            num_az_angles=self.num_az_angles,
            num_el_angles=self.num_el_angles,
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=self.heatmap_mode,
            covariance_matrix_time_constant_s=sf_to_tc(
                self.covariance_matrix_smoothing_factor, HEATMAP_FALLBACK_UPDATE_RATE
            ),
            high_pass_filter_time_constant_s=sf_to_tc(
                self.high_pass_filter_smoothing_factor, HEATMAP_FALLBACK_UPDATE_RATE
            ),
            normalized_heat_cutoff=self.normalized_heat_cutoff,
            max_2d_heat=self.max_2d_heat,
            log_scale_output=self.log_scale_output,
            # update_count is removed
        )


@attrs.mutable
class HeatmapConfig_v1(HeatmapConfigCommon):
    heatmap_mode: HeatmapConfig.HeatmapMode = attrs.field(converter=HeatmapConfig.HeatmapMode)
    covariance_matrix_time_constant_s: float
    high_pass_filter_time_constant_s: float
    normalized_heat_cutoff: float = attrs.field(default=0.75)
    max_2d_heat: t.Optional[int] = attrs.field(default=None)
    log_scale_output: bool = attrs.field(default=False)

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=HeatmapConfig.HeatmapMode.DISTANCE,
            covariance_matrix_time_constant_s=0.5,
            high_pass_filter_time_constant_s=1.5,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=30,
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
            heatmap_mode=self.heatmap_mode,
            covariance_matrix_time_constant_s=self.covariance_matrix_time_constant_s,
            high_pass_filter_time_constant_s=self.high_pass_filter_time_constant_s,
            # normalized_heat_cutoff, max_2d_heat, log_scale_output moved to HeatmapPlotConfig
        )


def migrate_legacy(old: config_legacy.HeatmapConfigLegacy) -> HeatmapConfig_v0:
    return HeatmapConfig_v0(
        az_angle_range=old.az_angle_range,
        el_angle_range=old.el_angle_range,
        num_az_angles=old.num_az_angles,
        num_el_angles=old.num_el_angles,
        antenna_array=old.antenna_array,
        heatmap_mode=old.heatmap_mode,
        covariance_matrix_smoothing_factor=old.covariance_matrix_smoothing_factor,
        high_pass_filter_smoothing_factor=old.high_pass_filter_smoothing_factor,
        # Beamformingmethod is removed
        update_count=old.update_count,
    )


heatmap_config_timeline = (
    config_legacy.heatmap_config_timeline.epoch(
        HeatmapConfig_v0,
        migrate_legacy,
        fail=[],
    )
    .load(str, HeatmapConfig_v0.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(HeatmapConfig_v1, HeatmapConfig_v0.migrate, fail=[])
    .load(str, HeatmapConfig_v1.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(HeatmapConfig, HeatmapConfig_v1.migrate, fail=[])
    .load(str, HeatmapConfig.from_json, fail=tm.common_exceptions.FROM_JSON)
)
