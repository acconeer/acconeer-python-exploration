# Copyright (c) Acconeer AB, 2025
# All rights reserved
from __future__ import annotations

import copy
import typing as t

import attrs
import numpy as np

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    RLG_PER_HWAAS_MAP,
    calc_processing_gain,
    get_distance_filter_edge_margin,
    select_prf,
)

from ._aggregator import ProcessorSpec
from ._processors import MeasurementType, Processor, ProcessorConfig, ThresholdMethod


if t.TYPE_CHECKING:
    from ._detector import DetectorConfig, ReflectorShape


_MIN_LEAKAGE_FREE_DIST_M = {
    a121.Profile.PROFILE_1: 0.12,
    a121.Profile.PROFILE_2: 0.28,
    a121.Profile.PROFILE_3: 0.56,
    a121.Profile.PROFILE_4: 0.76,
    a121.Profile.PROFILE_5: 1.28,
}
_MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN = 4.0
_VALID_STEP_LENGTHS = [1, 2, 3, 4, 6, 8, 12, 24]
_NUM_SUBSWEEPS_IN_SENSOR_CONFIG = 4
_HWAAS_MIN_DISTANCE = 1.0
_MAX_HWAAS = 511
_MIN_HWAAS = 1


@attrs.frozen(kw_only=True)
class SubsweepGroupPlan:
    step_length: int = attrs.field()
    breakpoints: list[int] = attrs.field()
    profile: a121.Profile = attrs.field()
    hwaas: list[int] = attrs.field()


Plan = dict[MeasurementType, list[SubsweepGroupPlan]]


def remove_dup(breakpoints: list[int]) -> list[int]:
    unique_bps = sorted(set(breakpoints[1:]))

    unique_bps = [breakpoints[0]] + unique_bps

    return unique_bps


def detector_config_to_session_config(
    config: DetectorConfig, sensor_ids: list[int]
) -> a121.SessionConfig:
    (session_config, _) = _detector_to_session_config_and_processor_specs(config, sensor_ids)
    return session_config


def detector_config_to_processor_specs(
    config: DetectorConfig, sensor_ids: list[int]
) -> list[ProcessorSpec]:
    (_, proc_specs) = _detector_to_session_config_and_processor_specs(config, sensor_ids)
    return proc_specs


def _detector_to_session_config_and_processor_specs(
    config: DetectorConfig,
    sensor_ids: list[int],
) -> tuple[a121.SessionConfig, list[ProcessorSpec]]:
    processor_specs = []
    groups = []
    group_index = 0

    plans = _create_group_plans(config)
    prf = _get_max_prf(plans)

    if MeasurementType.CLOSE_RANGE in plans:
        sensor_config = _close_subsweep_group_plans_to_sensor_config(
            plans[MeasurementType.CLOSE_RANGE]
        )
        groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})
        processor_specs.append(
            ProcessorSpec(
                processor_config=ProcessorConfig(
                    threshold_method=ThresholdMethod.RECORDED,
                    measurement_type=MeasurementType.CLOSE_RANGE,
                    threshold_sensitivity=config.threshold_sensitivity,
                    reflector_shape=config.reflector_shape,
                ),
                group_index=group_index,
                subsweep_indexes=[0, 1],
            )
        )
        group_index += 1

    if MeasurementType.FAR_RANGE in plans:
        (
            sensor_config,
            processor_specs_subsweep_indexes,
        ) = _far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
            plans[MeasurementType.FAR_RANGE], prf
        )
        groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})

        processor_config = ProcessorConfig(
            threshold_method=config.threshold_method,
            fixed_threshold_value=config.fixed_threshold_value,
            fixed_strength_threshold_value=config.fixed_strength_threshold_value,
            threshold_sensitivity=config.threshold_sensitivity,
            reflector_shape=config.reflector_shape,
        )

        for subsweep_indexes in processor_specs_subsweep_indexes:
            processor_specs.append(
                ProcessorSpec(
                    processor_config=processor_config,
                    group_index=group_index,
                    subsweep_indexes=subsweep_indexes,
                )
            )

    return (
        a121.SessionConfig(groups, extended=True, update_rate=config.update_rate),
        processor_specs,
    )


def _far_subsweep_group_plans_to_sensor_config_and_subsweep_indexes(
    subsweep_group_plans: list[SubsweepGroupPlan], prf: a121.PRF
) -> tuple[a121.SensorConfig, list[list[int]]]:
    subsweeps = []
    processor_specs_subsweep_indexes = []
    subsweep_idx = 0
    for plan in subsweep_group_plans:
        subsweep_indexes = []
        for bp_idx in range(len(plan.breakpoints) - 1):
            num_points = int(
                (plan.breakpoints[bp_idx + 1] - plan.breakpoints[bp_idx]) / plan.step_length
            )
            subsweeps.append(
                a121.SubsweepConfig(
                    start_point=plan.breakpoints[bp_idx],
                    num_points=num_points,
                    step_length=plan.step_length,
                    profile=plan.profile,
                    hwaas=plan.hwaas[bp_idx],
                    receiver_gain=10,
                    phase_enhancement=True,
                    iq_imbalance_compensation=True,
                    prf=prf,
                )
            )
            subsweep_indexes.append(subsweep_idx)
            subsweep_idx += 1
        processor_specs_subsweep_indexes.append(subsweep_indexes)
    return (
        a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=1),
        processor_specs_subsweep_indexes,
    )


def _close_subsweep_group_plans_to_sensor_config(
    plan_: list[SubsweepGroupPlan],
) -> a121.SensorConfig:
    (plan,) = plan_
    subsweeps = []
    subsweeps.append(
        a121.SubsweepConfig(
            start_point=0,
            num_points=1,
            step_length=1,
            profile=a121.Profile.PROFILE_4,
            hwaas=plan.hwaas[0],
            receiver_gain=15,
            phase_enhancement=True,
            iq_imbalance_compensation=True,
            enable_loopback=True,
            prf=a121.PRF.PRF_15_6_MHz,
        )
    )
    num_points = int((plan.breakpoints[1] - plan.breakpoints[0]) / plan.step_length)
    subsweeps.append(
        a121.SubsweepConfig(
            start_point=plan.breakpoints[0],
            num_points=num_points,
            step_length=plan.step_length,
            profile=plan.profile,
            hwaas=plan.hwaas[0],
            receiver_gain=5,
            phase_enhancement=True,
            iq_imbalance_compensation=True,
            prf=a121.PRF.PRF_15_6_MHz,
        )
    )
    return a121.SensorConfig(subsweeps=subsweeps, sweeps_per_frame=10)


def _get_max_prf(plans: dict[MeasurementType, list[SubsweepGroupPlan]]) -> a121.PRF:
    selected_prf = a121.PRF.PRF_19_5_MHz

    if MeasurementType.CLOSE_RANGE in plans:
        (plan,) = plans[MeasurementType.CLOSE_RANGE]
        prf = select_prf(plan.breakpoints[1], plan.profile)
        if prf.frequency < selected_prf.frequency:
            selected_prf = prf

    if MeasurementType.FAR_RANGE in plans:
        subsweep_group_plans = plans[MeasurementType.FAR_RANGE]
        for plan in subsweep_group_plans:
            for bp_idx in range(len(plan.breakpoints) - 1):
                prf = select_prf(plan.breakpoints[bp_idx + 1], plan.profile)
                if prf.frequency < selected_prf.frequency:
                    selected_prf = prf

    return selected_prf


def _create_group_plans(config: DetectorConfig) -> dict[MeasurementType, list[SubsweepGroupPlan]]:
    """
    Create dictionary containing group plans for close and far range measurements.

    - Close range measurement: Add Subsweep group if the user defined starting point is
    effected by the direct leakage.
    - Transition region: Add group plans to bridge the gap between the start of the far range
    measurement region(either end of close range region or user defined start_m) and the
    shortest measurable distance with max_profile, free from direct leakage interference.
    - Add group plan with max_profile. Increase HWAAS as a function of distance to maintain
    SNR throughout the sweep.
    """
    plans = {}

    # Determine shortest direct leakage free distance per profile
    min_dist_m = _calc_leakage_free_min_dist(config)

    close_range_transition_m = min_dist_m[a121.Profile.PROFILE_1]

    # Add close range group plan if applicable
    if config.close_range_leakage_cancellation and config.start_m < close_range_transition_m:
        plans[MeasurementType.CLOSE_RANGE] = _get_close_range_group_plan(
            close_range_transition_m, config
        )

    # Define transition group plans
    transition_subgroup_plans = _get_transition_group_plans(
        config, min_dist_m, MeasurementType.CLOSE_RANGE in plans
    )

    # The number of available subsweeps in the group with max profile.
    num_remaining_subsweeps = _NUM_SUBSWEEPS_IN_SENSOR_CONFIG - len(transition_subgroup_plans)

    # No neighbours if no close range measurement or transition groups defined.
    has_neighboring_subsweep = (
        MeasurementType.CLOSE_RANGE in plans or len(transition_subgroup_plans) != 0
    )

    # Define group plans with max profile
    max_profile_subgroup_plans = _get_max_profile_group_plans(
        config, min_dist_m, has_neighboring_subsweep, num_remaining_subsweeps
    )

    far_subgroup_plans = transition_subgroup_plans + max_profile_subgroup_plans

    if len(far_subgroup_plans) != 0:
        plans[MeasurementType.FAR_RANGE] = far_subgroup_plans

    return plans


def _get_transition_group_plans(
    config: DetectorConfig,
    min_dist_m: dict[a121.Profile, float],
    has_close_range_measurement: bool,
) -> list[SubsweepGroupPlan]:
    """Define the transition segment group plans.

    The purpose of the transition group is to bridge the gap between the start point of the
    far measurement region and the point where max_profile can be used without interference
    of direct leakage.

    The transition region can consist of maximum two subsweeps, where the first utilize profile
    1 and the second profile 3. Whether both, one or none is used depends on the user provided
    detector config.

    If close_range_leakage_cancellation is set to False, the first group plan should use
    the user provided starting point as start, as there is no close range leakage cancellation
    measurement.
    """
    transition_profiles = [
        profile
        for profile in [a121.Profile.PROFILE_1, a121.Profile.PROFILE_3]
        if profile.value < config.max_profile.value
    ]
    transition_profiles.append(config.max_profile)

    transition_subgroup_plans: list[SubsweepGroupPlan] = []

    for i in range(len(transition_profiles) - 1):
        profile = transition_profiles[i]
        next_profile = transition_profiles[i + 1]

        is_first_group_plan = len(transition_subgroup_plans) == 0
        start_m = None
        if (
            not config.close_range_leakage_cancellation
            and is_first_group_plan
            and config.start_m < min_dist_m[next_profile]
        ):
            start_m = config.start_m

        elif config.start_m < min_dist_m[next_profile] and min_dist_m[profile] < config.end_m:
            start_m = max(min_dist_m[profile], config.start_m)

        if start_m is not None:
            end_m = min(config.end_m, min_dist_m[next_profile])
            has_neighbour = (
                has_close_range_measurement or not is_first_group_plan,
                min_dist_m[next_profile] < end_m,
            )

            transition_subgroup_plans.append(
                _create_group_plan(profile, config, [start_m, end_m], has_neighbour, False)
            )

    return transition_subgroup_plans


def _get_max_profile_group_plans(
    config: DetectorConfig,
    min_dist_m: dict[a121.Profile, float],
    has_neighboring_subsweep: bool,
    num_remaining_subsweeps: int,
) -> list[SubsweepGroupPlan]:
    """Define far range group plans with max_profile

    Divide the measurement range from the shortest leakage free distance of max_profile to
    the end point into equidistance segments and assign HWAAS according to the radar equation
    to maintain SNR throughout the sweep.

    Note, special case when max profile is set to 1 and close range leakage cancellation is not
    used. In this cas, the start of the subsweep is set to the user defined starting point. For
    other max profiles, this is handled in _get_transition_group_plans.
    """

    if min_dist_m[config.max_profile] < config.end_m or (
        not config.close_range_leakage_cancellation
        and config.max_profile == a121.Profile.PROFILE_1
    ):
        if not config.close_range_leakage_cancellation and (
            config.max_profile == a121.Profile.PROFILE_1
        ):
            subsweep_start_m = config.start_m
        else:
            subsweep_start_m = max([config.start_m, min_dist_m[config.max_profile]])

        breakpoints_m = np.linspace(
            subsweep_start_m,
            config.end_m,
            num_remaining_subsweeps + 1,
        ).tolist()

        return [
            _create_group_plan(
                config.max_profile,
                config,
                breakpoints_m,
                (has_neighboring_subsweep, False),
                False,
            )
        ]
    else:
        return []


def _get_close_range_group_plan(
    transition_m: float, config: DetectorConfig
) -> list[SubsweepGroupPlan]:
    """Define the group plan for close range measurements.

    The close range measurement always use profile 1 to minimize direct leakage region.
    """
    profile = a121.Profile.PROFILE_1
    # Select the end point as the shorter of the user provided end point or the transition
    # point.
    close_range_group_end_m = min(transition_m, config.end_m)
    # No left neighbour as this is the first subsweep when close range measurement is
    # applicable.
    has_neighbour = (False, transition_m < config.end_m)
    return [
        _create_group_plan(
            profile,
            config,
            [config.start_m, close_range_group_end_m],
            has_neighbour,
            True,
        )
    ]


def _create_group_plan(
    profile: a121.Profile,
    config: DetectorConfig,
    breakpoints_m: list[float],
    has_neighbour: tuple[bool, bool],
    is_close_range_measurement: bool,
) -> SubsweepGroupPlan:
    """Creates a group plan."""
    step_length = _limit_step_length(profile, config.max_step_length)
    breakpoints = _m_to_points(breakpoints_m, step_length)

    breakpoints = remove_dup(breakpoints)

    hwaas = _calculate_hwaas(
        profile,
        breakpoints,
        config.signal_quality,
        step_length,
        config.reflector_shape,
    )

    extended_breakpoints = _add_margin_to_breakpoints(
        profile=profile,
        step_length=step_length,
        base_bpts=breakpoints,
        has_neighbour=has_neighbour,
        config=config,
        is_close_range_measurement=is_close_range_measurement,
    )

    return SubsweepGroupPlan(
        step_length=step_length,
        breakpoints=extended_breakpoints,
        profile=profile,
        hwaas=hwaas,
    )


def _m_to_points(breakpoints_m: list[float], step_length: int) -> list[int]:
    bpts_m = np.array(breakpoints_m)
    start_point_m = bpts_m[0]
    start_point_p = int(start_point_m / APPROX_BASE_STEP_LENGTH_M)

    breakpoint_offsets_p_fractional = (bpts_m - start_point_m) / APPROX_BASE_STEP_LENGTH_M
    breakpoints_p_fractional = breakpoint_offsets_p_fractional + start_point_p

    return (  # type: ignore[no-any-return]
        ((np.round(breakpoints_p_fractional) // step_length) * step_length).astype(int).tolist()
    )


def _calculate_hwaas(
    profile: a121.Profile,
    breakpoints: list[int],
    signal_quality: float,
    step_length: int,
    reflector_shape: ReflectorShape,
) -> list[int]:
    rlg_per_hwaas = RLG_PER_HWAAS_MAP[profile]
    hwaas = []
    for idx in range(len(breakpoints) - 1):
        processing_gain = calc_processing_gain(profile, step_length)
        subsweep_end_point_m = max(
            APPROX_BASE_STEP_LENGTH_M * breakpoints[idx + 1],
            _HWAAS_MIN_DISTANCE,
        )
        rlg = (
            signal_quality
            + reflector_shape.exponent * 10 * np.log10(subsweep_end_point_m)
            - np.log10(processing_gain)
        )
        hwaas_in_subsweep = int(round(10 ** ((rlg - rlg_per_hwaas) / 10)))
        hwaas.append(np.clip(hwaas_in_subsweep, _MIN_HWAAS, _MAX_HWAAS))
    return hwaas


def _add_margin_to_breakpoints(
    profile: a121.Profile,
    step_length: int,
    base_bpts: list[int],
    has_neighbour: tuple[bool, bool],
    config: DetectorConfig,
    is_close_range_measurement: bool,
) -> list[int]:
    """
    Add points to segment edges based on their position.

    1. Add one margin to each segment for distance filter initialization
    2. Add an additional margin to segments with neighboring segments for segment overlap
    """

    margin_p = get_distance_filter_edge_margin(profile, step_length) * step_length
    left_margin = margin_p
    right_margin = margin_p

    if has_neighbour[0]:
        left_margin += margin_p

    if has_neighbour[1]:
        right_margin += margin_p

    if config.threshold_method == ThresholdMethod.CFAR and not is_close_range_measurement:
        cfar_margin = Processor.calc_cfar_margin(profile, step_length) * step_length
        left_margin += cfar_margin
        right_margin += cfar_margin

    bpts = copy.copy(base_bpts)
    bpts[0] -= left_margin
    bpts[-1] += right_margin

    return bpts


def _calc_leakage_free_min_dist(config: DetectorConfig) -> dict[a121.Profile, float]:
    """This function calculates the shortest leakage free distance per profile, for all profiles
    up to max_profile"""
    min_dist_m = {}
    for profile, min_dist in _MIN_LEAKAGE_FREE_DIST_M.items():
        min_dist_m[profile] = min_dist
        if config.threshold_method == ThresholdMethod.CFAR:
            step_length = _limit_step_length(profile, config.max_step_length)
            cfar_margin_m = (
                Processor.calc_cfar_margin(profile, step_length)
                * step_length
                * APPROX_BASE_STEP_LENGTH_M
            )
            min_dist_m[profile] += cfar_margin_m

        if profile == config.max_profile:
            # All profiles up to max_profile has been added. Break and return result.
            break

    return min_dist_m


def _limit_step_length(profile: a121.Profile, user_limit: t.Optional[int]) -> int:
    """
    Calculates step length based on user defined step length and selected profile.

    The step length must yield minimum _MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN number of points
    in the span of the FWHM of the envelope.

    If the step length is <24, return the valid step length(defined by
    _VALID_STEP_LENGTHS) that is closest to, but not longer than the limit.

    If the limit is 24<=, return the multiple of 24 that is
    closest, but not longer than the limit.
    """

    fwhm_p = ENVELOPE_FWHM_M[profile] / APPROX_BASE_STEP_LENGTH_M
    limit = int(fwhm_p / _MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN)

    if user_limit is not None:
        limit = min(user_limit, limit)

    if limit < _VALID_STEP_LENGTHS[-1]:
        idx_closest = np.sum(np.array(_VALID_STEP_LENGTHS) <= limit) - 1
        return int(_VALID_STEP_LENGTHS[idx_closest])
    else:
        return int((limit // _VALID_STEP_LENGTHS[-1]) * _VALID_STEP_LENGTHS[-1])
