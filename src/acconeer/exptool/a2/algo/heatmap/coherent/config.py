# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

from enum import Enum, auto

import attrs
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool import a2
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool.a2.algo._utils import HEATMAP_FALLBACK_UPDATE_RATE, sf_to_tc
from acconeer.exptool.a2.algo.heatmap import config_legacy
from acconeer.exptool.a2.algo.heatmap.coherent.plot_config import CoherentHeatmapPlotConfig
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
        def _missing_(cls, value: object) -> te.Self | None:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    heatmap_mode: HeatmapMode = attrs.field(converter=HeatmapMode)
    """Heatmap mode to use"""

    high_pass_filter_time_constant_s: float
    """Time constant for the high-pass filter."""

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=cls.HeatmapMode.DISTANCE,
            high_pass_filter_time_constant_s=1.5,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=30,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
        )


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
    class DisplayMode(Enum):
        """Display mode. ``ABSOLUTE`` returns absolute of complex value. ``ANGLE`` returns complex argument."""

        ABSOLUTE = auto()
        ANGLE = auto()

        @classmethod
        def _missing_(cls, value: object) -> te.Self | None:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    heatmap_mode: HeatmapConfig.HeatmapMode = attrs.field(converter=HeatmapConfig.HeatmapMode)
    """Heatmap mode to use"""

    high_pass_filter_smoothing_factor: float
    """Exponential smoothing factor of the high-pass filter"""

    display_mode: DisplayMode = attrs.field(converter=DisplayMode)
    """
    If the output should be absolute or angular (phase).
    Complex value (which contains both parts) can be found in separate output.
    """

    normalized_heat_cutoff: float = attrs.field(default=0.75)
    max_2d_heat: int | None = attrs.field(default=None)
    log_scale_output: bool = attrs.field(default=False)

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=HeatmapConfig.HeatmapMode.DISTANCE,
            high_pass_filter_smoothing_factor=0.99,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=23,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
            display_mode=cls.DisplayMode.ANGLE,
        )

    def migrate(self) -> HeatmapConfig_v1:
        return HeatmapConfig_v1(
            az_angle_range=self.az_angle_range,
            el_angle_range=self.el_angle_range,
            num_az_angles=self.num_az_angles,
            num_el_angles=self.num_el_angles,
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=self.heatmap_mode,
            high_pass_filter_time_constant_s=sf_to_tc(
                self.high_pass_filter_smoothing_factor, HEATMAP_FALLBACK_UPDATE_RATE
            ),
            display_mode=CoherentHeatmapPlotConfig.DisplayMode.ANGLE,
            normalized_heat_cutoff=self.normalized_heat_cutoff,
            max_2d_heat=self.max_2d_heat,
            log_scale_output=self.log_scale_output,
        )


@attrs.mutable
class HeatmapConfig_v1(HeatmapConfigCommon):
    heatmap_mode: HeatmapConfig.HeatmapMode = attrs.field(converter=HeatmapConfig.HeatmapMode)
    high_pass_filter_time_constant_s: float
    display_mode: CoherentHeatmapPlotConfig.DisplayMode = attrs.field(
        converter=CoherentHeatmapPlotConfig.DisplayMode
    )
    normalized_heat_cutoff: float = attrs.field(default=0.75)
    max_2d_heat: int | None = attrs.field(default=None)
    log_scale_output: bool = attrs.field(default=False)

    @classmethod
    def default(cls) -> te.Self:
        return cls(
            antenna_array=a2.AntennaArray.AP212,
            heatmap_mode=HeatmapConfig.HeatmapMode.DISTANCE,
            high_pass_filter_time_constant_s=1.5,
            az_angle_range=(-60.0, 60.0),
            num_az_angles=30,
            el_angle_range=(-0.0, 0.0),
            num_el_angles=1,
            display_mode=CoherentHeatmapPlotConfig.DisplayMode.ANGLE,  # kept for migration deserialization
        )

    def migrate(self) -> HeatmapConfig:
        return HeatmapConfig(
            az_angle_range=self.az_angle_range,
            el_angle_range=self.el_angle_range,
            num_az_angles=self.num_az_angles,
            num_el_angles=self.num_el_angles,
            antenna_array=self.antenna_array,
            heatmap_mode=self.heatmap_mode,
            high_pass_filter_time_constant_s=self.high_pass_filter_time_constant_s,
            # display_mode moved to CoherentHeatmapPlotConfig
            # normalized_heat_cutoff, max_2d_heat, log_scale_output moved to HeatmapPlotConfig
        )


def migrate_legacy(old: config_legacy.HeatmapConfigLegacy) -> HeatmapConfig_v0:
    return HeatmapConfig_v0(
        az_angle_range=old.az_angle_range,
        el_angle_range=old.el_angle_range,
        num_az_angles=old.num_az_angles,
        num_el_angles=old.num_el_angles,
        antenna_array=old.antenna_array,
        heatmap_mode=old.heatmap_mode.name,
        high_pass_filter_smoothing_factor=old.high_pass_filter_smoothing_factor,
        # Beamformingmethod is removed
        display_mode=HeatmapConfig_v0.DisplayMode.ANGLE,
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
