# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved
from __future__ import annotations

import typing as t

import attrs
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils as core_utils

from . import domain
from .lookup import Module, Sensor


_S = t.TypeVar("_S")
_T = t.TypeVar("_T")
_U = t.TypeVar("_U")
_ms = _mA = 1e-3
_us = _uA = 1e-6


@te.overload
def _interleave(
    __a: t.Iterable[_S],
    __b: t.Iterable[_T],
    __c: t.Iterable[_U],
) -> t.Iterator[t.Union[_S, _T, _U]]: ...


@te.overload
def _interleave(
    __a: t.Iterable[_S],
    __b: t.Iterable[_T],
) -> t.Iterator[t.Union[_S, _T]]: ...


def _interleave(*iterables: t.Iterable[_T]) -> t.Iterator[_T]:
    iterators = [iter(i) for i in iterables]

    while True:
        for iterator in iterators:
            try:
                yield next(iterator)
            except StopIteration:
                return


class Algorithm(te.Protocol):
    def decide_control(
        self,
        frame_actives: t.Sequence[t.Mapping[int, domain.EnergyRegion]],
        frame_idles: list[dict[int, domain.SimpleRegion]],
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[Sensor.LowerIdleState],
        sensor: Sensor,
        module: Module,
    ) -> t.Iterable[domain.EnergyRegion]: ...


class SparseIq(Algorithm):
    def decide_control(
        self,
        frame_actives: t.Sequence[t.Mapping[int, domain.EnergyRegion]],
        frame_idles: list[dict[int, domain.SimpleRegion]],
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[Sensor.LowerIdleState],
        sensor: Sensor,
        module: Module,
    ) -> t.Iterable[domain.EnergyRegion]:
        active_iter = core_utils.iterate_extended_structure_values(frame_actives)
        idle_list = list(core_utils.iterate_extended_structure_values(frame_idles))[:-1]

        if lower_idle_state == Sensor.IdleState.OFF:
            yield off_exit(sensor, module)
        elif lower_idle_state == Sensor.IdleState.HIBERNATE:
            yield hibernate_exit(last_inter_frame_idle_state(config), sensor, module)

        yield from _interleave(
            active_iter,
            idle_list,
        )

        if lower_idle_state == Sensor.IdleState.OFF:
            yield off_enter(sensor, module)
        elif lower_idle_state == Sensor.IdleState.HIBERNATE:
            yield hibernate_enter(sensor, module)


class Presence(Algorithm):
    _PROCESSING_SECONDS_PER_POINT = 11.28125e-6

    def decide_control(
        self,
        frame_actives: t.Sequence[t.Mapping[int, domain.EnergyRegion]],
        frame_idles: list[dict[int, domain.SimpleRegion]],
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[Sensor.LowerIdleState],
        sensor: Sensor,
        module: Module,
    ) -> t.Iterable[domain.EnergyRegion]:
        (sensor_config,) = config.groups[0].values()
        num_points = sum([subsweep.num_points for subsweep in sensor_config.subsweeps])
        points_measured = num_points * sensor_config.sweeps_per_frame
        process_duration = points_measured * self._PROCESSING_SECONDS_PER_POINT

        yield from SparseIq().decide_control(
            frame_actives, frame_idles, config, lower_idle_state, sensor, module
        )
        yield domain.SimpleRegion(
            module.currents[Module.PowerState.PROCESSING],
            process_duration,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description="Presence processing",
        )


class Distance(Algorithm):
    _PROCESSING_SECONDS_PER_POINT = 12e-6

    @classmethod
    def processing_region(
        cls,
        sensor_config: a121.SensorConfig,
        sensor: Sensor,
        module: Module,
    ) -> domain.SimpleRegion:
        static_duration = 2.5e-3

        num_points = sum(ssc.num_points for ssc in sensor_config.subsweeps)
        return domain.SimpleRegion(
            (
                module.currents[Module.PowerState.PROCESSING]
                + sensor.inter_frame_currents[sensor_config.inter_frame_idle_state]
            ),
            duration=static_duration + num_points * cls._PROCESSING_SECONDS_PER_POINT,
            tag=domain.EnergyRegion.Tag.PROCESSING,
            description=f"Distance processing ({num_points} points)",
        )

    @staticmethod
    def recalculate_idle(
        idle_and_processing: tuple[domain.SimpleRegion, domain.EnergyRegion],
    ) -> t.Optional[domain.SimpleRegion]:
        idle, processing = idle_and_processing

        if idle.duration < processing.duration:
            return None
        else:
            return attrs.evolve(idle, duration=idle.duration - processing.duration)

    def decide_control(
        self,
        frame_actives: t.Sequence[t.Mapping[int, domain.EnergyRegion]],
        frame_idles: list[dict[int, domain.SimpleRegion]],
        config: a121.SessionConfig,
        lower_idle_state: t.Optional[Sensor.LowerIdleState],
        sensor: Sensor,
        module: Module,
    ) -> t.Iterator[domain.EnergyRegion]:
        processings = core_utils.map_over_extended_structure(
            lambda sc: self.processing_region(sc, sensor=sensor, module=module),
            config.groups,
        )

        idles = core_utils.map_over_extended_structure(
            self.recalculate_idle,
            core_utils.zip_extended_structures(
                frame_idles,
                processings,
            ),
        )

        if lower_idle_state == Sensor.IdleState.OFF:
            yield off_exit(sensor, module)
        elif lower_idle_state == Sensor.IdleState.HIBERNATE:
            yield hibernate_exit(last_inter_frame_idle_state(config), sensor, module)

        for region in _interleave(
            core_utils.iterate_extended_structure_values(frame_actives),
            core_utils.iterate_extended_structure_values(processings),
            core_utils.iterate_extended_structure_values(idles),
        ):
            if region is not None:
                yield region

        if lower_idle_state == Sensor.IdleState.OFF:
            yield off_enter(sensor, module)
        elif lower_idle_state == Sensor.IdleState.HIBERNATE:
            yield hibernate_enter(sensor, module)


def hibernate_enter(
    sensor: Sensor,
    module: Module,
) -> domain.SimpleRegion:
    """
    Returns a region describing the sequence of hibernating
    """
    set_hibernate_register = domain.SimpleRegion(
        module.currents[Module.PowerState.IO],
        110 * _us,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Tell sensor to go into hibernation",
    )
    wfi = domain.SimpleRegion(
        module.currents[Module.PowerState.AWAKE],
        2 * _ms,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Wait for interrupt",
    )

    real_enter = domain.CompositeRegion(
        (set_hibernate_register, wfi),
        description="Go down to hibernation",
    )

    return domain.SimpleRegion(
        real_enter.average_current,
        real_enter.duration,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Go down to hibernation",
    )


def hibernate_exit(
    recent_inter_frame_idle: a121.IdleState,
    sensor: Sensor,
    module: Module,
) -> domain.SimpleRegion:
    """
    Returns a region describing the sequence of waking up from hibernation
    """
    start_interfaces = domain.SimpleRegion(
        module.currents[Module.PowerState.IO],
        0.1 * _ms,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Starting interfaces",
    )
    wfi = domain.SimpleRegion(
        module.currents[Module.PowerState.AWAKE]
        + sensor.inter_frame_currents[recent_inter_frame_idle],
        2 * _ms,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Wait for interrupt",
    )
    spi_sanity = domain.SimpleRegion(
        module.currents[Module.PowerState.IO]
        + sensor.inter_frame_currents[recent_inter_frame_idle],
        300 * _us,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Spi sanity",
    )

    real_exit = domain.CompositeRegion(
        (start_interfaces, wfi, spi_sanity), description="Wake up from hibernate"
    )

    return domain.SimpleRegion(
        real_exit.average_current,
        real_exit.duration,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Wake up from hibernate",
    )


def off_enter(
    sensor: Sensor,
    module: Module,
) -> domain.SimpleRegion:
    """
    Describes the power region of powering down (entering off)
    """
    wfi = domain.SimpleRegion(
        module.currents[Module.PowerState.AWAKE],
        2 * _ms,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Enter off",
    )

    return wfi


def off_exit(
    sensor: Sensor,
    module: Module,
) -> domain.SimpleRegion:
    """
    Returns a region describing the sequence of waking up from off
    """

    return domain.SimpleRegion(
        10.51 * _mA,
        4 * _ms,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Wake up from off",
    )


def last_inter_frame_idle_state(config: a121.SessionConfig) -> a121.IdleState:
    last_sensor_config = list(config.groups[-1].values())[-1]
    return last_sensor_config.inter_frame_idle_state
