# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

import attrs

from acconeer.exptool.a121._core.utils import zip_extended_structures

from ._core import IdleState, Metadata, SensorConfig, SessionConfig


@attrs.frozen
class _SessionPerformanceCalc:
    session_config: SessionConfig = attrs.field()
    extended_metadata: Optional[list[dict[int, Metadata]]] = attrs.field()

    @property
    def update_duration(self) -> float:
        if self.extended_metadata is None:
            raise ValueError("Metadata is None")

        extended_structures = zip_extended_structures(
            self.session_config.groups, self.extended_metadata
        )

        update_duration = 0.0

        for extended_structure in extended_structures:
            update_duration += max(
                _SensorPerformanceCalc(
                    sensor_config, metadata, self.session_config.update_rate
                ).frame_active_duration
                for sensor_config, metadata in extended_structure.values()
            )

        return update_duration

    @property
    def update_rate(self) -> float:
        if self.session_config.update_rate is not None:
            return self.session_config.update_rate
        elif (
            not self.session_config.extended
            and self.session_config.sensor_config.frame_rate is not None
        ):
            return self.session_config.sensor_config.frame_rate
        else:
            return 1.0 / self.update_duration


@attrs.frozen
class _SensorPerformanceCalc:
    """Calculates performance metrics from config and metadata

    The figures are preliminary, approximate, and not guaranteed. Based on conservative
    measurements taken in room temperature.
    """

    sensor_config: SensorConfig = attrs.field()
    metadata: Optional[Metadata] = attrs.field()
    update_rate: Optional[float] = attrs.field()

    @property
    def spf(self) -> int:
        return self.sensor_config.sweeps_per_frame

    @property
    def sweep_rate(self) -> float:
        if self.sensor_config.sweep_rate is not None:
            return self.sensor_config.sweep_rate
        else:
            if self.metadata is None:
                raise ValueError("Metadata is None")
            return self.metadata.max_sweep_rate

    @property
    def sweep_period(self) -> float:
        return 1 / self.sweep_rate

    @property
    def sweep_active_duration(self) -> float:
        if self.metadata is None:
            raise ValueError("Metadata is None")
        return 1 / self.metadata.max_sweep_rate

    @property
    def sweep_idle_duration(self) -> float:
        return self.sweep_period - self.sweep_active_duration

    @property
    def frame_active_duration(self) -> float:
        return self.sweep_period * self.spf

    @property
    def frame_rate(self) -> float:
        max_rate = self.sweep_rate / self.spf

        if self.update_rate is not None:
            rate = self.update_rate
        elif self.sensor_config.frame_rate is not None:
            rate = self.sensor_config.frame_rate
        else:
            rate = max_rate

        return min(rate, max_rate)

    @property
    def frame_period(self) -> float:
        return 1 / self.frame_rate

    @property
    def frame_idle_duration(self) -> float:
        return self.frame_period - self.frame_active_duration

    @property
    def active_current(self) -> float:
        return 85e-3

    @property
    def inter_sweep_idle_current(self) -> float:
        return self._get_idle_current(self.sensor_config.inter_sweep_idle_state)

    @property
    def inter_frame_idle_current(self) -> float:
        return self._get_idle_current(self.sensor_config.inter_frame_idle_state)

    @property
    def sweep_active_charge(self) -> float:
        return self.sweep_active_duration * self.active_current

    @property
    def sweep_idle_charge(self) -> float:
        return self.sweep_idle_duration * self.inter_sweep_idle_current

    @property
    def sweep_charge(self) -> float:
        return self.sweep_active_charge + self.sweep_idle_charge

    @property
    def frame_active_charge(self) -> float:
        return self.sweep_charge * self.spf

    @property
    def frame_idle_charge(self) -> float:
        return self.frame_idle_duration * self.inter_frame_idle_current

    @property
    def frame_charge(self) -> float:
        return self.frame_active_charge + self.frame_idle_charge

    @property
    def average_current(self) -> float:
        return self.frame_charge / self.frame_period

    @staticmethod
    def _get_idle_current(idle_state: IdleState) -> float:
        return {
            IdleState.READY: 70.0e-3,
            IdleState.SLEEP: 1.8e-3,
            IdleState.DEEP_SLEEP: 1.2e-3,
        }[idle_state]
