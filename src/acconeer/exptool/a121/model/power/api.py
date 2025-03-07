# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved
"""
API for generating power regions (for more info see ./domain.py).

The different functions return regions based on the figures below:

    ^
    |    ___           ___
    |    |X|           |X|
    |    |X|           |X|
    | ---|X|-----------|X|----
    +-------------------------->

          ^ |_________| ^
          3      2      3
    |______________________ ...
                 1

1. Session (indefinitely repeats 2. and 3.)
2. Group idle (Idle/Hibernate/Off)
3. Group active is described by the figure below

    ^
    |      ___     ___
    |      |X|-----|X|     _____
    |    __|X|XXXXX|X|__   |XXX|
    | ---|X|X|XXXXX|X|X|---|XXX|---
    +---------------------------->

          ^ ^ |___| ^ ^    |___|
          4 2   3   2 4      5*
         |_____________________|
                  1
1. Group active
2. Frame active for every SensorConfig in the SessionConfig
3. Frame idle. Idles with the previous (chronologically)
               SensorConfig's inter_frame_idle_state
4. Going to/returning from Idle/Hibernate/Off.
5. Algorithm Processing.
*. Different algorithms (passed via the "algorithm"-parameter in most functions)
   are free to decide the ordering of the regions in Group active
   (including addition of processing regions like 4). This is needed to model
   different algorithms' control flow. (See ./algo.py)

Going deeper down into, the frame active consists of sweep active and sweep idle, etc.
"""

from __future__ import annotations

import collections
import typing as t

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils as core_utils

from . import algo, domain
from . import dependency_injection as di
from .lookup import Module, Sensor


_T = t.TypeVar("_T")

_ms = _mA = 1e-3
_us = _uA = 1e-6


def configured_rate(config: a121.SessionConfig) -> t.Optional[float]:
    """
    Returns the configured rate of the session config.
    Either returns the update_rate or a frame_rate.
    """
    if config.update_rate is not None:
        return config.update_rate

    frame_rates = set(
        sensor_config.frame_rate
        for sensor_config in core_utils.iterate_extended_structure_values(config.groups)
        if sensor_config.frame_rate is not None
    )

    if len(frame_rates) == 1:
        (frame_rate,) = frame_rates
        return frame_rate
    else:
        return None


def is_high_speed_mode(config: a121.SensorConfig) -> bool:
    hsm_profiles = {a121.Profile.PROFILE_3, a121.Profile.PROFILE_4, a121.Profile.PROFILE_5}
    return (
        config.num_subsweeps == 1
        and config.profile in hsm_profiles
        and config.inter_sweep_idle_state == a121.IdleState.READY
        and not config.continuous_sweep_mode
    )


def power_state(
    state: Sensor.LowerIdleState,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.SimpleRegion:
    """
    Returns a simple region that describes being in the given power state
    """
    return domain.SimpleRegion(
        (sensor.inter_frame_currents[state] + module.currents[Module.PowerState.ASLEEP]),
        duration,
        description=state.name,
        tag=domain.EnergyRegion.Tag.IDLE,
    )


def subsweep_active(
    config: a121.SubsweepConfig,
    high_speed_mode: bool,
    subsweep_index: int,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.SimpleRegion:
    """
    Returns a region that describes measuring a single subsweep (no overheads)
    """
    if high_speed_mode:
        overhead_duration = sensor.high_speed_mode_overheads[Sensor.FixedOverhead.SUBSWEEP]
    else:
        overhead_duration = sensor.normal_overheads[Sensor.FixedOverhead.SUBSWEEP]

    sample_duration = sensor.sample_durations[config.profile][config.prf]
    point_duration = (
        config.hwaas * sample_duration + sensor.point_overheads[config.profile][config.prf]
    )
    subsweep_duration = config.num_points * point_duration + (
        3 * sample_duration + overhead_duration
    )

    return domain.SimpleRegion(
        (sensor.measure_currents[config.profile] + module.currents[Module.PowerState.AWAKE]),
        subsweep_duration,
        domain.EnergyRegion.Tag.MEASURE,
        description=f"Subsweep {subsweep_index} measure ({config.profile.name}, {config.num_points} points)",
    )


def sweep_active(
    config: a121.SensorConfig,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.EnergyRegion:
    """
    Returns a region that describes measuring a sweep, subsweeps and subsweep overhead included
    """
    high_speed_mode = is_high_speed_mode(config)
    if high_speed_mode:
        overhead_duration = sensor.high_speed_mode_overheads[Sensor.FixedOverhead.SWEEP]
    else:
        overhead_duration = sensor.normal_overheads[Sensor.FixedOverhead.SWEEP]

    overhead = domain.SimpleRegion(
        module.currents[Module.PowerState.AWAKE],
        duration=overhead_duration,
        description="inter-subsweep overhead",
        tag=domain.EnergyRegion.Tag.OVERHEAD,
    )

    return overhead.join(
        (
            subsweep_active(subsweep, high_speed_mode, idx, sensor, module)
            for idx, subsweep in enumerate(config.subsweeps, start=1)
        ),
        description="Sweep active",
    )


def sweep_idle(
    config: a121.SensorConfig,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.SimpleRegion:
    """
    Returns a region that describes the idling between sweeps
    """
    current = module.currents[Module.PowerState.AWAKE]

    if is_high_speed_mode(config):
        current += sensor.inter_sweep_currents_high_speed_mode[config.inter_sweep_idle_state]
        description = f"Sweep idle ({config.inter_sweep_idle_state.name}, High speed mode)"
    else:
        current += sensor.inter_sweep_currents[config.inter_sweep_idle_state]
        description = f"Sweep idle ({config.inter_sweep_idle_state.name})"

    return domain.SimpleRegion(
        current,
        duration,
        tag=domain.EnergyRegion.Tag.IDLE,
        description=description,
    )


def frame_active(
    config: a121.SensorConfig,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.CompositeRegion:
    """
    Returns a region that describes the active part of a frame (sweeps and sweep idles)
    """
    if is_high_speed_mode(config):
        overhead_duration = sensor.high_speed_mode_overheads[Sensor.FixedOverhead.FRAME]
    else:
        overhead_duration = sensor.normal_overheads[Sensor.FixedOverhead.FRAME]

    frame_overhead = domain.SimpleRegion(
        module.currents[Module.PowerState.AWAKE],  # FIXME: guessed
        overhead_duration,
        tag=domain.EnergyRegion.Tag.OVERHEAD,
        description="Frame overhead",
    )

    arbitrary_setup = domain.SimpleRegion(
        (
            # looks to be about this
            module.currents[Module.PowerState.AWAKE]
            + sensor.inter_frame_currents[config.inter_frame_idle_state]
        ),
        sensor.pre_measure_setup_duration,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Setup",
    )

    read = domain.SimpleRegion(
        (
            (module.currents[Module.PowerState.IO] + module.currents[Module.PowerState.AWAKE]) / 2
            + sensor.inter_frame_currents[config.inter_frame_idle_state]
        ),
        sensor.read_duration,
        tag=domain.EnergyRegion.Tag.COMMUNICATION,
        description="Read",
    )

    active = sweep_active(config, sensor, module)
    minimum_transition_time = sensor.time_for_measure_transition[config.inter_sweep_idle_state]

    if config.sweep_rate is None:
        inter_sweep_idle_duration = minimum_transition_time
    else:
        inter_sweep_idle_duration = max(
            minimum_transition_time, 1 / config.sweep_rate - active.duration
        )

    return domain.CompositeRegion(
        (
            arbitrary_setup,
            frame_overhead,
            sweep_idle(
                config,
                inter_sweep_idle_duration,
                sensor,
                module,
            ).join([active] * config.sweeps_per_frame, description="Frame measurement"),
            read,
        ),
        description="Frame active",
    )


def frame_idle(
    inter_frame_idle_state: a121.IdleState,
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.SimpleRegion:
    """
    Returns a region that describes the idling between frames
    """
    return domain.SimpleRegion(
        (
            sensor.inter_frame_currents[inter_frame_idle_state]
            + module.currents[Module.PowerState.AWAKE]
        ),
        duration,
        tag=domain.EnergyRegion.Tag.IDLE,
        description=f"Frame idle ({inter_frame_idle_state.name})",
    )


def group_active(
    session_config: a121.SessionConfig,
    lower_idle_state: t.Optional[Sensor.LowerIdleState],
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.CompositeRegion:
    """
    Describes the active part of a group.
    """
    frame_actives = [
        {sid: frame_active(sensor_config, sensor, module) for sid, sensor_config in group.items()}
        for group in session_config.groups
    ]

    frame_idles = [
        {
            sid: frame_idle(
                sensor_config.inter_frame_idle_state,
                sensor.time_for_measure_transition[sensor_config.inter_frame_idle_state],
                sensor,
                module,
            )
            for sid, sensor_config in group.items()
        }
        for group in session_config.groups
    ]

    return domain.CompositeRegion(
        tuple(
            algorithm.decide_control(
                frame_actives,
                frame_idles,
                session_config,
                lower_idle_state,
                sensor,
                module,
            )
        ),
        description="Measure groups active",
    )


def group_idle(
    inter_group_power_state: t.Union[a121.IdleState, Sensor.LowerIdleState],
    duration: float,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> domain.SimpleRegion:
    """
    Returns a region that describes the idling between groups
    """
    if inter_group_power_state is None:
        module_power_state = Module.PowerState.AWAKE
    else:
        module_power_state = Module.PowerState.ASLEEP

    return domain.SimpleRegion(
        (
            sensor.inter_frame_currents[inter_group_power_state]
            + module.currents[module_power_state]
        ),
        duration,
        tag=domain.EnergyRegion.Tag.IDLE,
        description=f"Group idle ({inter_group_power_state.name})",
    )


def session_generator(
    session_config: a121.SessionConfig,
    lower_idle_state: t.Optional[Sensor.LowerIdleState],
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> t.Iterator[domain.EnergyRegion]:
    """
    Indefinitely simulates the session, yielding region per region
    """
    active = group_active(session_config, lower_idle_state, algorithm, sensor, module)

    rate = configured_rate(session_config)

    regions: list[domain.EnergyRegion]
    if rate is None:
        regions = [active]
    else:
        duration = 1 / rate - active.duration

        if duration > 0:
            idle = group_idle(
                lower_idle_state or algo.last_inter_frame_idle_state(session_config),
                duration,
                sensor=sensor,
                module=module,
            )
            regions = [active, idle]
        else:
            regions = [active]

    while True:
        yield from regions


def session(
    session_config: a121.SessionConfig,
    lower_idle_state: t.Optional[Sensor.LowerIdleState],
    duration: t.Optional[float] = None,
    num_actives: t.Optional[int] = None,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
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
        lower_idle_state,
        algorithm,
        sensor,
        module,
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

    if duration is not None:
        return sequence.truncate(duration)
    else:
        return sequence


def converged_average_current(
    session_config: a121.SessionConfig,
    lower_idle_state: t.Optional[Sensor.LowerIdleState],
    absolute_tolerance: float,
    convergence_window: int = 10,
    algorithm: algo.Algorithm = di.DEFAULT_ALGO,
    sensor: Sensor = di.DEFAULT_SENSOR,
    module: Module = di.DEFAULT_MODULE,
) -> float:
    """
    Simulates the session until the average current has been within 'absolute_tolerance'.
    for 'convergence_window' iterations.
    """
    gen = session_generator(
        session_config,
        lower_idle_state,
        algorithm,
        sensor,
        module,
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
