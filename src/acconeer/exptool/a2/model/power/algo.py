# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

import collections.abc
import math
import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool import a2
from acconeer.exptool.a2.algo.heatmap.capon.config import HeatmapConfig as HeatmapCaponConfig
from acconeer.exptool.a2.algo.heatmap.coherent.config import (
    HeatmapConfig as HeatmapCoherentConfig,
)
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon
from acconeer.exptool.a2.algo.heatmap.conventional.config import (
    HeatmapConfig as HeatmapConventionalConfig,
)
from acconeer.exptool.a2.algo.heatmap.robust_capon.config import (
    HeatmapConfig as HeatmapRobustCaponConfig,
)

from . import domain, frozen_subclasses
from .common import get_idle_rs_current
from .lookup import SensorConstants


_S = t.TypeVar("_S")
_T = t.TypeVar("_T")
_U = t.TypeVar("_U")
_ms = _mA = 1e-3
_us = _uA = 1e-6


def _count_bits(number: int) -> int:
    return bin(number).count("1")


class Algorithm(collections.abc.Hashable, te.Protocol):
    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion: ...


@attrs.frozen
class SparseIq(Algorithm):
    # For A121 decide_control was used to implement more complex flow for detectors.
    # This might be needed once we introduce Ref.Apps./Detectors with complex flows.
    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion:
        sensor_config = config.sensor_config
        points_measured = 0
        for subsweep in sensor_config.subsweeps:
            points_measured += (
                subsweep.num_points
                * sensor_config.sweeps_per_frame
                * _count_bits(subsweep.rx_antenna_mask)
                * _count_bits(subsweep.tx_antenna_mask)
            )

        process_duration = sensor.iq_processing_fixed

        if sensor_config.jitter_compensation:
            process_duration += points_measured * sensor.iq_processing_per_point

        return domain.SimpleRegion(
            sensor.aps_active_currents[aps_active_state] + get_idle_rs_current(config, sensor),
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Sparse IQ processing",
        )


def _covariance_channel_factor(num_channels: int) -> float:
    """How the measured Capon, Conventional and Robust Capon cost grows with channels

    They share one covariance matrix per range point and apply a steering vector
    per grid point, so the measured cost sits between those terms. The exponent
    is a fit, not an operation count.
    """
    return num_channels * math.sqrt(num_channels)


def _heatmap_processing_duration(
    sensor_config: a2.SensorConfig,
    heatmap_config: HeatmapConfigCommon,
    processing_per_param: float,
    update_per_point: float,
    channel_factor: t.Callable[[int], float],
) -> float:
    """Scale the measured per-point costs of a heatmap processor to a config

    ``channel_factor`` is how the cost per grid point grows with the number of
    virtual channels, which is what separates the processors.
    """
    processing_params = 0.0
    sweep_points = 0

    for subsweep in sensor_config.subsweeps:
        processing_params += (
            subsweep.num_points
            * heatmap_config.num_az_angles
            * heatmap_config.num_el_angles
            * channel_factor(subsweep.num_channels)
        )
        sweep_points += subsweep.num_points * subsweep.num_channels

    return processing_params * processing_per_param + sweep_points * update_per_point


def _ensure_frozen_capon_config(
    c: HeatmapCaponConfig,
) -> frozen_subclasses.FrozenHeatmapCaponConfig:
    if isinstance(c, frozen_subclasses.FrozenHeatmapCaponConfig):
        return c
    return frozen_subclasses.FrozenHeatmapCaponConfig.from_dict(c.to_dict())


@attrs.frozen
class HeatmapCapon(Algorithm):
    # Converter wraps mutable HeatmapCaponConfig into a frozen variant so the
    # algorithm itself stays hashable (required by @functools.cache on
    # group_active). Direct instantiation with either a mutable or frozen
    # config works.
    #
    # `eq=repr` makes attrs use repr(heatmap_config) for __eq__ and __hash__.
    # The HeatmapConfig tree references AntennaArray (an Enum whose attrs
    # mutable parent zeros out __hash__), so we can't structurally hash the
    # config; repr produces a deterministic string instead.
    heatmap_config: frozen_subclasses.FrozenHeatmapCaponConfig = attrs.field(
        converter=_ensure_frozen_capon_config,
        eq=repr,
    )

    @classmethod
    def create(cls, config: HeatmapCaponConfig) -> te.Self:
        # Kept for backwards compatibility; equivalent to the constructor.
        return cls(config)

    # For A121 decide_control was used to implement more complex flow for detectors.
    # This might be needed once we introduce Ref.Apps./Detectors with complex flows.
    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion:
        sparse_iq_processing = SparseIq().processing(config, aps_active_state, sensor)

        process_duration = _heatmap_processing_duration(
            config.sensor_config,
            self.heatmap_config,
            sensor.capon_processing_per_param,
            sensor.capon_update_per_point,
            channel_factor=_covariance_channel_factor,
        )

        capon_heatmap_processing = domain.SimpleRegion(
            sensor.aps_active_currents[aps_active_state] + get_idle_rs_current(config, sensor),
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Capon heatmap processing",
        )

        return domain.CompositeRegion(
            (sparse_iq_processing, capon_heatmap_processing), description="Processing"
        )


def _coherent_channel_factor(num_channels: int) -> float:
    """The coherent beamformer is a plain sum over the channels"""
    return float(num_channels)


def _ensure_frozen_coherent_config(
    c: HeatmapCoherentConfig,
) -> frozen_subclasses.FrozenHeatmapCoherentConfig:
    if isinstance(c, frozen_subclasses.FrozenHeatmapCoherentConfig):
        return c
    return frozen_subclasses.FrozenHeatmapCoherentConfig.from_dict(c.to_dict())


@attrs.frozen
class HeatmapCoherent(Algorithm):
    # See HeatmapCapon.heatmap_config for why we converter+eq=repr here.
    heatmap_config: frozen_subclasses.FrozenHeatmapCoherentConfig = attrs.field(
        converter=_ensure_frozen_coherent_config,
        eq=repr,
    )

    @classmethod
    def create(cls, config: HeatmapCoherentConfig) -> te.Self:
        # Mirrors the other heatmap algorithms, which the outputs construct this way.
        return cls(config)

    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion:
        sparse_iq_processing = SparseIq().processing(config, aps_active_state, sensor)

        process_duration = _heatmap_processing_duration(
            config.sensor_config,
            self.heatmap_config,
            sensor.coherent_processing_per_param,
            sensor.coherent_update_per_point,
            channel_factor=_coherent_channel_factor,
        )

        coherent_heatmap_processing = domain.SimpleRegion(
            sensor.aps_active_currents[aps_active_state] + get_idle_rs_current(config, sensor),
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Coherent heatmap processing",
        )

        return domain.CompositeRegion(
            (sparse_iq_processing, coherent_heatmap_processing), description="Processing"
        )


def _ensure_frozen_conventional_config(
    c: HeatmapConventionalConfig,
) -> frozen_subclasses.FrozenHeatmapConventionalConfig:
    if isinstance(c, frozen_subclasses.FrozenHeatmapConventionalConfig):
        return c
    return frozen_subclasses.FrozenHeatmapConventionalConfig.from_dict(c.to_dict())


@attrs.frozen
class HeatmapConventional(Algorithm):
    # See HeatmapCapon.heatmap_config for why we converter+eq=repr here.
    heatmap_config: frozen_subclasses.FrozenHeatmapConventionalConfig = attrs.field(
        converter=_ensure_frozen_conventional_config,
        eq=repr,
    )

    @classmethod
    def create(cls, config: HeatmapConventionalConfig) -> te.Self:
        # Kept for backwards compatibility; equivalent to the constructor.
        return cls(config)

    # For A121 decide_control was used to implement more complex flow for detectors.
    # This might be needed once we introduce Ref.Apps./Detectors with complex flows.
    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion:
        sparse_iq_processing = SparseIq().processing(config, aps_active_state, sensor)

        process_duration = _heatmap_processing_duration(
            config.sensor_config,
            self.heatmap_config,
            sensor.conventional_processing_per_param,
            sensor.conventional_update_per_point,
            channel_factor=_covariance_channel_factor,
        )

        conventional_heatmap_processing = domain.SimpleRegion(
            sensor.aps_active_currents[aps_active_state] + get_idle_rs_current(config, sensor),
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Conventional heatmap processing",
        )

        return domain.CompositeRegion(
            (sparse_iq_processing, conventional_heatmap_processing), description="Processing"
        )


def _ensure_frozen_robust_capon_config(
    c: HeatmapRobustCaponConfig,
) -> frozen_subclasses.FrozenHeatmapRobustCaponConfig:
    if isinstance(c, frozen_subclasses.FrozenHeatmapRobustCaponConfig):
        return c
    return frozen_subclasses.FrozenHeatmapRobustCaponConfig.from_dict(c.to_dict())


@attrs.frozen
class HeatmapRobustCapon(Algorithm):
    # See HeatmapCapon.heatmap_config for why we converter+eq=repr here.
    heatmap_config: frozen_subclasses.FrozenHeatmapRobustCaponConfig = attrs.field(
        converter=_ensure_frozen_robust_capon_config,
        eq=repr,
    )

    @classmethod
    def create(cls, config: HeatmapRobustCaponConfig) -> te.Self:
        # Kept for backwards compatibility; equivalent to the constructor.
        return cls(config)

    # For A121 decide_control was used to implement more complex flow for detectors.
    # This might be needed once we introduce Ref.Apps./Detectors with complex flows.
    def processing(
        self,
        config: a2.SessionConfig,
        aps_active_state: SensorConstants.ApsActiveState,
        sensor: SensorConstants,
    ) -> domain.EnergyRegion:
        sparse_iq_processing = SparseIq().processing(config, aps_active_state, sensor)

        process_duration = _heatmap_processing_duration(
            config.sensor_config,
            self.heatmap_config,
            sensor.robust_capon_processing_per_param,
            sensor.robust_capon_update_per_point,
            channel_factor=_covariance_channel_factor,
        )

        robust_capon_heatmap_processing = domain.SimpleRegion(
            sensor.aps_active_currents[aps_active_state] + get_idle_rs_current(config, sensor),
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Robust Capon heatmap processing",
        )

        return domain.CompositeRegion(
            (sparse_iq_processing, robust_capon_heatmap_processing), description="Processing"
        )
