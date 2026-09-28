# Copyright (c) Acconeer AB, 2024-2026
# All rights reserved

from __future__ import annotations

import typing as t
from enum import Enum, auto

import attrs
import attrs.validators as av
import typing_extensions as te
from attributes_doc import attributes_doc

from acconeer.exptool import a2
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin


def to_tuple(v: t.Any) -> tuple[float, float]:
    return tuple(v)


@attributes_doc
@attrs.mutable
class HeatmapConfigLegacy(AttrsMappingTransformsMixin):
    class HeatmapMode(Enum):
        DISTANCE = auto()
        MOVEMENT = auto()

        @classmethod
        def _missing_(cls, value: object) -> te.Self | None:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    class BeamformingMethod(Enum):
        GENERAL = auto()
        CAPON = auto()

        @classmethod
        def _missing_(cls, value: object) -> te.Self | None:
            if isinstance(value, str):
                return find_by_name(cls, value)
            else:
                return None

    antenna_array: a2.AntennaArray = attrs.field(converter=a2.AntennaArray)

    heatmap_mode: HeatmapMode = attrs.field(converter=HeatmapMode)

    covariance_matrix_smoothing_factor: float

    high_pass_filter_smoothing_factor: float

    beamforming_method: BeamformingMethod = attrs.field(converter=BeamformingMethod)

    update_count: int

    az_angle_range: tuple[float, float] = attrs.field(
        validator=[av.min_len(2), av.max_len(2)],
        converter=to_tuple,
    )

    el_angle_range: tuple[float, float] = attrs.field(
        validator=[av.min_len(2), av.max_len(2)],
        converter=to_tuple,
    )

    num_az_angles: int = attrs.field(validator=av.gt(0))

    num_el_angles: int = attrs.field(validator=av.gt(0))

    normalized_heat_cutoff: float

    max_2d_heat: int | None = attrs.field(default=100000000)

    log_scale_output: bool = attrs.field(default=False)

    def to_dict(self) -> dict[str, t.Any]:
        return attrs.asdict(self, recurse=False)

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(
            **{
                **dict_repr,
                "antenna_array": a2.AntennaArray(dict_repr["antenna_array"]),
            }
        )


@attrs.mutable
class _PluginConfig_v0(AttrsMappingTransformsMixin):
    antenna_array: a2.AntennaArray = attrs.field(converter=a2.AntennaArray)
    heatmap_mode: HeatmapConfigLegacy.HeatmapMode = attrs.field(
        converter=HeatmapConfigLegacy.HeatmapMode
    )
    covariance_matrix_smoothing_factor: float
    high_pass_filter_smoothing_factor: float
    beamforming_method: HeatmapConfigLegacy.BeamformingMethod = attrs.field(
        converter=HeatmapConfigLegacy.BeamformingMethod
    )
    update_count: int
    azimuth_angle_step: int
    elevation_angle_step: int
    num_azimuth_angles: int
    num_elevation_angles: int
    normalized_heat_cutoff: float
    max_2d_heat: int | None = attrs.field(default=100000000)
    log_scale_output: bool = attrs.field(default=False)

    def migrate(self) -> _PluginConfig_v1:
        return _PluginConfig_v1(
            # Name change
            az_angle_step=self.azimuth_angle_step,
            el_angle_step=self.elevation_angle_step,
            num_az_angles=self.num_azimuth_angles,
            num_el_angles=self.num_elevation_angles,
            # The rest are the same.
            antenna_array=self.antenna_array,
            heatmap_mode=self.heatmap_mode,
            covariance_matrix_smoothing_factor=self.covariance_matrix_smoothing_factor,
            high_pass_filter_smoothing_factor=self.high_pass_filter_smoothing_factor,
            beamforming_method=self.beamforming_method,
            update_count=self.update_count,
            normalized_heat_cutoff=self.normalized_heat_cutoff,
            max_2d_heat=self.max_2d_heat,
            log_scale_output=self.log_scale_output,
        )


@attrs.mutable
class _PluginConfig_v1(AttrsMappingTransformsMixin):
    antenna_array: a2.AntennaArray = attrs.field(converter=a2.AntennaArray)
    heatmap_mode: HeatmapConfigLegacy.HeatmapMode = attrs.field(
        converter=HeatmapConfigLegacy.HeatmapMode
    )
    covariance_matrix_smoothing_factor: float
    high_pass_filter_smoothing_factor: float
    beamforming_method: HeatmapConfigLegacy.BeamformingMethod = attrs.field(
        converter=HeatmapConfigLegacy.BeamformingMethod
    )
    update_count: int
    az_angle_step: int
    el_angle_step: int
    num_az_angles: int
    num_el_angles: int
    normalized_heat_cutoff: float
    max_2d_heat: int | None = attrs.field(default=100000000)
    log_scale_output: bool = attrs.field(default=False)

    def migrate(self) -> HeatmapConfigLegacy:
        return HeatmapConfigLegacy(
            # Value change
            az_angle_range=(
                -self.az_angle_step * self.num_az_angles,
                self.az_angle_step * self.num_az_angles,
            ),
            el_angle_range=(
                -self.el_angle_step * self.num_el_angles,
                self.el_angle_step * self.num_el_angles,
            ),
            # Num angles means all angles now, instead of number per side.
            num_az_angles=self.num_az_angles * 2 + 1,
            num_el_angles=self.num_el_angles * 2 + 1,
            # The rest are the same.
            antenna_array=self.antenna_array,
            heatmap_mode=self.heatmap_mode,
            covariance_matrix_smoothing_factor=self.covariance_matrix_smoothing_factor,
            high_pass_filter_smoothing_factor=self.high_pass_filter_smoothing_factor,
            beamforming_method=self.beamforming_method,
            update_count=self.update_count,
            normalized_heat_cutoff=self.normalized_heat_cutoff,
            max_2d_heat=self.max_2d_heat,
            log_scale_output=self.log_scale_output,
        )


heatmap_config_timeline = (
    tm.start(_PluginConfig_v0)
    .load(str, _PluginConfig_v0.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(_PluginConfig_v1, _PluginConfig_v0.migrate, fail=[])
    .load(str, _PluginConfig_v1.from_json, fail=tm.common_exceptions.FROM_JSON)
    .nop()
    .epoch(HeatmapConfigLegacy, _PluginConfig_v1.migrate, fail=[])
    .load(str, HeatmapConfigLegacy.from_json, fail=tm.common_exceptions.FROM_JSON)
)
