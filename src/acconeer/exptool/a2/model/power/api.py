# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
"""
API for generating power regions (for more info see ./domain.py).

The different functions return regions based on the figures below:

    ^
    |     ___                ___
    |     |X|   _____        |X| _____
    |     |X|X| |XXX|-|------|X| |XXX|
    | --|X|X|X|-|XXX|X|XXXXXX|X|-|XXX|---
    +------------------------------------>

         ^ ^   ^  ^  ^|______| ^
         2 3   4  5  6   7
    |_________________________ ...
                 1

1. Session (indefinitely repeats 2. through 6.)
2. Wake up from sleep/idle
3. Frame active
4. If update rate is set we will turn off RS before processing
5. Algorithm Processing. (See ./algo.py)
6. Enter sleep/idle
7. Frame idle (APS Sleep / RS Idle)

Going deeper down into, the frame active consists of sweep active and sweep idle, etc.
"""

from __future__ import annotations

import collections
import functools
import itertools
import typing as t

import attrs
import numpy as np

from acconeer.exptool import a2

from . import algo, domain, frozen_subclasses
from . import dependency_injection as di
from .common import get_idle_rs_current
from .domain import CurrentBreakdown
from .lookup import Sensor, SensorConstants


_T = t.TypeVar("_T")

_ms = _mA = 1e-3
_us = _uA = 1e-6


def configured_rate(config: a2.SessionConfig) -> t.Optional[float]:
    """
    Returns the configured rate of the session config.
    Either returns the update_rate or a frame_rate.
    """
    if config.update_rate is not None:
        return config.update_rate

    return config.sensor_config.frame_rate


def get_idle_aps_current(
    config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> CurrentBreakdown:
    """
    Returns the APS current while idling between frames
    """
    sensor_data = sensor.get_sensor_data()
    if config.update_rate is not None:
        return sensor_data.inter_frame_aps_currents[aps_sleep_state]
    return sensor_data.inter_frame_aps_currents[aps_idle_state]


def is_high_speed_mode(config: a2.SensorConfig) -> bool:
    return (
        config.num_subsweeps == 1
        and config.sweeps_per_frame > 1
        and not config.jitter_compensation
    )


def power_state(
    rs_idle_state: a2.IdleState,
    aps_idle_state: SensorConstants.ApsSleepState,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.SimpleRegion:
    """
    Returns a simple region that describes being in the given power state
    """
    sensor_data = sensor.get_sensor_data()
    return domain.SimpleRegion(
        (
            sensor_data.inter_frame_rs_currents[rs_idle_state]
            + sensor_data.inter_frame_aps_currents[aps_idle_state]
        ),
        duration,
        description=rs_idle_state.name,
        tag=domain.EnergyRegion.Tag.IDLE,
    )


def subsweep_active(
    config: a2.SubsweepConfig,
    subsweep_index: int,
    aps_idle_state: SensorConstants.ApsIdleState,
    high_speed_mode: bool,
    inter_sweep_idle_state: a2.IdleState,
    jitter_comp: bool,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.EnergyRegion:
    """
    Returns a region that describes measuring a single subsweep
    """
    sensor_data = sensor.get_sensor_data()
    if high_speed_mode:
        subsweep_setup_time = sensor_data.subsweep_setup_times_hsm[inter_sweep_idle_state]
        rs_idle_current = sensor_data.inter_sweep_currents_hsm[a2.IdleState.ARMED]
    else:
        subsweep_setup_time = sensor_data.subsweep_setup_time
        rs_idle_current = sensor_data.inter_sweep_currents[a2.IdleState.ARMED]

    subsweep_overhead = domain.SimpleRegion(
        (
            sensor_data.inter_frame_aps_currents[SensorConstants.ApsIdleState.APS_HF_WFI]
            + rs_idle_current
        ),
        duration=subsweep_setup_time,
        description="Subsweep overhead",
        tag=domain.EnergyRegion.Tag.OVERHEAD,
    )

    sample_duration = sensor_data.sample_durations[config.profile][config.prf]

    num_tx_antennas = bin(config.tx_antenna_mask).count("1")
    num_rx_antennas = bin(config.rx_antenna_mask).count("1")

    rx_current_saved = CurrentBreakdown.zero()

    # Handle case where not all RX antennas are used and subtract the unused antennas currents
    if num_rx_antennas != 4:
        disabled_rx_channels = [i for i in range(4) if not (config.rx_antenna_mask >> i) & 1]
        for rx_channel in disabled_rx_channels:
            rx_current_saved += sensor_data.rx_antenna_current[config.profile][rx_channel]

    subsweep_duration = (
        4 * int(np.sum(config.hwaas_points)) * num_tx_antennas + 2
    ) * sample_duration

    if jitter_comp:
        subsweep_duration += (
            sensor_data.jitter_compensation_duration + sensor_data.subsweep_setup_time_loopback
        )

    subsweep_active = domain.SimpleRegion(
        (
            sensor_data.measure_currents[config.profile][config.prf]
            + sensor_data.inter_frame_aps_currents[SensorConstants.ApsIdleState.APS_HF_WFI]
            - rx_current_saved
        ),
        subsweep_duration,
        domain.EnergyRegion.Tag.MEASURE,
        description=f"Subsweep {subsweep_index} measure ({config.profile.name}, {config.num_points} points), {num_tx_antennas} TX antennas",
    )

    return domain.CompositeRegion((subsweep_overhead, subsweep_active))


def sweep_active(
    config: a2.SensorConfig,
    aps_idle_state: SensorConstants.ApsIdleState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.EnergyRegion:
    """
    Returns a region that describes measuring a sweep, subsweeps and subsweep overhead included
    """
    high_speed_mode = is_high_speed_mode(config)
    regions: list[domain.EnergyRegion] = []

    sensor_data = sensor.get_sensor_data()
    if high_speed_mode:
        rs_idle_current = sensor_data.inter_sweep_currents_hsm[a2.IdleState.ARMED]
    else:
        rs_idle_current = sensor_data.inter_sweep_currents[a2.IdleState.ARMED]
        sweep_setup_time = sensor_data.sweep_setup_times[config.inter_sweep_idle_state]

        sweep_overhead = domain.SimpleRegion(
            (
                sensor_data.inter_frame_aps_currents[SensorConstants.ApsIdleState.APS_HF_WFI]
                + rs_idle_current
            ),
            duration=sweep_setup_time,
            description="Sweep overhead",
            tag=domain.EnergyRegion.Tag.OVERHEAD,
        )
        regions.append(sweep_overhead)

    regions += [
        subsweep_active(
            subsweep,
            idx,
            aps_idle_state,
            high_speed_mode,
            config.inter_sweep_idle_state,
            (idx == len(config.subsweeps) and config.jitter_compensation),
            sensor,
        )
        for idx, subsweep in enumerate(config.subsweeps, start=1)
    ]

    return domain.CompositeRegion(tuple(regions))


def sweep_idle(
    config: a2.SensorConfig,
    aps_idle_state: SensorConstants.ApsIdleState,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.SimpleRegion:
    """
    Returns a region that describes the idling between sweeps
    """
    high_speed_mode = is_high_speed_mode(config)

    sensor_data = sensor.get_sensor_data()
    if high_speed_mode:
        rs_idle_current = sensor_data.inter_sweep_currents_hsm[config.inter_sweep_idle_state]
    else:
        rs_idle_current = sensor_data.inter_sweep_currents[config.inter_sweep_idle_state]

    return domain.SimpleRegion(
        (
            sensor_data.inter_frame_aps_currents[SensorConstants.ApsIdleState.APS_HF_WFI]
            + rs_idle_current
        ),
        duration,
        tag=domain.EnergyRegion.Tag.IDLE,
        description=f"Sweep idle ({config.inter_sweep_idle_state.name})",
    )


def exit_idle(
    config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    rate = configured_rate(config)

    sensor_data = sensor.get_sensor_data()
    domains = []

    if rate is not None:
        if aps_sleep_state in [
            SensorConstants.ApsSleepState.SHALLOW_SLEEP,
            SensorConstants.ApsSleepState.DEEP_SLEEP,
            SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP,
        ]:
            domains.append(
                attrs.evolve(
                    sensor_data.aps_sleep_wakeup_state[
                        aps_sleep_state  # type: ignore[index]
                    ],
                    tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                    description="Wake up from APS sleep",
                )
            )
        else:
            if aps_sleep_state == SensorConstants.ApsIdleState.APS_LF_WFI:
                domains.append(
                    attrs.evolve(
                        sensor_data.aps_lf_to_hf_state,
                        tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                        description="LF->HF",
                    )
                )
            if aps_sleep_state == SensorConstants.ApsIdleState.APS_MF_WFI:
                domains.append(
                    attrs.evolve(
                        sensor_data.aps_mf_to_hf_state,
                        tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                        description="MF->HF",
                    )
                )
        # Common for all sleep states
        domains.append(
            attrs.evolve(
                sensor_data.radar_power_on_state,
                tag=domain.EnergyRegion.Tag.RS_INITIALIZATION,
                description="Radar power on",
            )
        )
        if aps_sleep_state in [
            SensorConstants.ApsSleepState.DEEP_SLEEP,
            SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP,
        ]:
            domains.append(
                attrs.evolve(
                    sensor_data.calibration_state,
                    tag=domain.EnergyRegion.Tag.CALIBRATION,
                    description="Radar calibration",
                )
            )
            # Calibration sets up RS for the prepare step, so use radar_prepare_state
            domains.append(
                attrs.evolve(
                    sensor_data.radar_prepare_state,
                    tag=domain.EnergyRegion.Tag.RS_INITIALIZATION,
                    description="Radar prepare",
                )
            )
        else:
            # No calibration: use the prepare-with-RS-init variant
            domains.append(
                attrs.evolve(
                    sensor_data.radar_prepare_rs_init_state,
                    tag=domain.EnergyRegion.Tag.RS_INITIALIZATION,
                    description="Radar prepare",
                )
            )
    else:
        domains.append(
            domain.SimpleRegion(  # TODO
                10 * _mA,
                1.0 * _ms,
                tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                description="Exit sleep",
            )
        )

    return domain.CompositeRegion(
        tuple(domains),
        "Exit sleep",
    )


def radar_off(
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.SimpleRegion:
    return attrs.evolve(
        sensor.get_sensor_data().radar_power_off_state,
        tag=domain.EnergyRegion.Tag.RS_INITIALIZATION,
        description="Radar power off",
    )


def enter_idle(
    config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_active_state: SensorConstants.ApsActiveState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    rate = configured_rate(config)
    sensor_data = sensor.get_sensor_data()

    domains = []

    if rate is not None:
        if aps_sleep_state in [
            SensorConstants.ApsSleepState.SHALLOW_SLEEP,
            SensorConstants.ApsSleepState.DEEP_SLEEP,
            SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP,
        ]:
            domains.append(
                attrs.evolve(
                    sensor_data.aps_go_to_sleep_state[
                        aps_sleep_state  # type: ignore[index]
                    ],
                    tag=domain.EnergyRegion.Tag.IDLE,
                    description="Enter APS sleep",
                )
            )
        else:
            if aps_sleep_state == SensorConstants.ApsIdleState.APS_LF_WFI:
                domains.append(
                    attrs.evolve(
                        sensor_data.aps_hf_to_lf_state,
                        tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                        description="HF->LF",
                    )
                )
            if aps_sleep_state == SensorConstants.ApsIdleState.APS_MF_WFI:
                domains.append(
                    attrs.evolve(
                        sensor_data.aps_hf_to_mf_state,
                        tag=domain.EnergyRegion.Tag.APS_INITIALIZATION,
                        description="HF->MF",
                    )
                )
    else:
        domains.append(
            domain.SimpleRegion(
                sensor_data.aps_active_currents[aps_active_state],
                1.0 * _ms,
                tag=domain.EnergyRegion.Tag.IDLE,
                description="Enter sleep",
            )
        )

    return domain.CompositeRegion(
        tuple(domains),
        "Enter sleep",
    )


def frame_start(
    config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> float:
    if config.update_rate is not None:
        return exit_idle(
            config, aps_sleep_state, aps_idle_state, aps_active_state, sensor
        ).duration
    else:
        return 0


def frame_active(
    config: a2.SessionConfig,
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    """
    Returns a region that describes the active part of a frame (sweeps and sweep idles)
    """

    active = sweep_active(config.sensor_config, aps_idle_state, sensor)

    if config.sensor_config.sweep_rate is None:
        inter_sweep_idle_duration = 0.0
    else:
        inter_sweep_idle_duration = max(0.0, 1 / config.sensor_config.sweep_rate - active.duration)

    return domain.CompositeRegion(
        (
            sweep_idle(
                config.sensor_config,
                aps_idle_state,
                inter_sweep_idle_duration,
                sensor,
            ).join(
                [active] * config.sensor_config.sweeps_per_frame, description="Frame measurement"
            ),
        ),
        description="Frame active",
    )


def frame_idle(
    config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.SimpleRegion:
    """
    Returns a region that describes the idling between frames
    """

    idle_rs_current = get_idle_rs_current(config, sensor.get_sensor_data())
    idle_aps_current = get_idle_aps_current(config, aps_sleep_state, aps_idle_state, sensor)

    return domain.SimpleRegion(
        idle_aps_current + idle_rs_current,
        duration,
        tag=domain.EnergyRegion.Tag.IDLE,
        description=f"Frame idle ({aps_sleep_state.name if config.update_rate is not None else config.sensor_config.inter_frame_idle_state.name})",
    )


def group_active(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    return _group_active(
        frozen_subclasses.FrozenSessionConfig.from_dict(session_config.to_dict()),
        aps_sleep_state,
        aps_idle_state,
        aps_active_state,
        algorithm,
        sensor,
    )


@functools.cache
def _group_active(
    session_config: frozen_subclasses.FrozenSessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    active = frame_active(session_config, aps_idle_state, aps_active_state, sensor)
    processing = algorithm.processing(session_config, aps_active_state, sensor.get_sensor_data())

    active_and_processing = domain.CompositeRegion(
        (
            active,
            processing,
        )
    )

    rate = configured_rate(session_config)

    regions: list[domain.EnergyRegion]
    if rate is None:
        regions = [active_and_processing]
    else:
        rs_off = radar_off(sensor)
        enter = enter_idle(session_config, aps_sleep_state, aps_active_state, sensor)
        exit = exit_idle(session_config, aps_sleep_state, aps_idle_state, aps_active_state, sensor)
        exit_and_active_and_rs_off_and_processing_and_enter = domain.CompositeRegion(
            (exit, active, rs_off, processing, enter),
        )
        if session_config.update_rate is not None:
            regions = [exit_and_active_and_rs_off_and_processing_and_enter]
        else:
            regions = [active_and_processing]

    return domain.CompositeRegion(tuple(regions))


def session_generator(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> t.Iterator[domain.EnergyRegion]:
    """
    Indefinitely simulates the session, yielding region per region
    """
    active = group_active(
        session_config,
        aps_sleep_state,
        aps_idle_state,
        aps_active_state,
        algorithm,
        sensor,
    )

    rate = configured_rate(session_config)

    regions: list[domain.EnergyRegion]
    regions = [active]
    if rate is not None:
        duration = 1 / rate - active.duration

        if duration > 0:
            idle = frame_idle(
                session_config,
                aps_sleep_state,
                aps_idle_state,
                aps_active_state,
                duration,
                sensor=sensor,
            )
            regions.append(idle)

    while True:
        yield from regions


def active_frame(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    """
    Returns a CompositeRegion covering exactly one active frame
    and one idle region.

    When the session has a configured update rate this is the active
    group (exit-idle + measure + enter-idle) followed by the
    inter-frame idle period.  When there is no configured rate it is
    just the active group with no idle region.
    """
    regions = list(
        itertools.islice(
            session_generator(
                session_config,
                aps_sleep_state,
                aps_idle_state,
                aps_active_state,
                algorithm,
                sensor,
            ),
            2,
        )
    )
    return domain.CompositeRegion(tuple(regions))


def session(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    duration: t.Optional[float] = None,
    num_actives: t.Optional[int] = None,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    """
    Models the first `duration` seconds of a session
    """
    regions: list[domain.EnergyRegion] = []
    elapsed_time = 0.0
    found_actives = 0

    if num_actives is None and duration is None:
        msg = "At least one of 'num_actives' and 'duration' needs to be not None"
        raise ValueError(msg)

    for region in session_generator(
        session_config,
        aps_sleep_state,
        aps_idle_state,
        aps_active_state,
        algorithm,
        sensor,
    ):
        regions += [region]
        elapsed_time += region.duration

        if not (
            isinstance(region, domain.SimpleRegion) and region.tag is domain.EnergyRegion.Tag.IDLE
        ):
            found_actives += 1

        if duration is not None and elapsed_time > duration:
            break
        if num_actives is not None and found_actives >= num_actives:
            break

    sequence = domain.CompositeRegion(
        tuple(regions),
        f"First {duration} seconds of session",
    )

    # dump_region(sequence)

    if duration is not None:
        return sequence.truncate(duration)
    else:
        return sequence


def converged_session(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    absolute_tolerance: float,
    convergence_window: int = 10,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> domain.CompositeRegion:
    """
    Simulates the session until the average current has converged,
    returning the full CompositeRegion.

    The underlying group_active() is cached via @functools.cache so
    repeated calls with the same arguments are cheap.
    """
    gen = session_generator(
        session_config,
        aps_sleep_state,
        aps_idle_state,
        aps_active_state,
        algorithm,
        sensor,
    )

    regions: list[domain.EnergyRegion] = []
    total_duration = 0.0
    cumulative_charge = 0.0
    average_currents: collections.deque[float] = collections.deque(maxlen=convergence_window)

    for region in gen:
        regions.append(region)
        cumulative_charge += region.charge
        total_duration += region.duration

        average_currents.append(cumulative_charge / total_duration)
        if len(average_currents) == convergence_window and all(
            ac - min(average_currents) < absolute_tolerance for ac in average_currents
        ):
            break

    return domain.CompositeRegion(tuple(regions), "Converged session")


def converged_average_current(
    session_config: a2.SessionConfig,
    aps_sleep_state: t.Union[SensorConstants.ApsIdleState, SensorConstants.ApsSleepState],
    aps_idle_state: SensorConstants.ApsIdleState,
    aps_active_state: SensorConstants.ApsActiveState,
    absolute_tolerance: float,
    convergence_window: int = 10,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
) -> float:
    """
    Simulates the session until the average current has been within 'absolute_tolerance'.
    for 'convergence_window' iterations.
    """
    gen = session_generator(
        session_config,
        aps_sleep_state,
        aps_idle_state,
        aps_active_state,
        algorithm,
        sensor,
    )

    first = next(gen)
    total_duration = first.duration
    cumulative_charge = first.charge
    average_currents = collections.deque([first.average_current], maxlen=convergence_window)

    for region in gen:
        cumulative_charge += region.charge
        total_duration += region.duration

        average_currents.append(cumulative_charge / total_duration)
        if len(average_currents) == convergence_window and all(
            ac - min(average_currents) < absolute_tolerance for ac in average_currents
        ):
            break

    return average_currents[-1]


def dump_region(region: domain.EnergyRegion, indent: str = "") -> None:
    if isinstance(region, domain.SimpleRegion):
        print(
            "\n".join(
                [
                    f"{indent}{region.description}",
                    f"{indent} - current:  {region.average_current * 1000:.3f} mA",
                    f"{indent} - duration: {region.duration * 1000:.3f} ms",
                ]
            )
        )
    elif isinstance(region, domain.CompositeRegion):
        print(
            f"{indent}{region.description: <{50 - len(indent)}} (avg. {region.average_current * 1000:.3f} mA, {region.duration * 1000:.3f} ms)"
        )
        for r in region.regions:
            dump_region(r, indent=indent + "|   ")
