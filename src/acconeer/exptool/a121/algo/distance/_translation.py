# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
from __future__ import annotations

import typing as t
from collections.abc import Iterator
from enum import Flag, auto

import attrs
import numpy as np
import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    RLG_PER_HWAAS_MAP,
    calc_processing_gain,
    get_distance_filter_edge_margin,
    select_prf_m,
)

from ._aggregator import ProcessorSpec
from ._processors import MeasurementType, ProcessorConfig, ThresholdMethod
from ._thresholds import CfarThreshold
from ._views import SubsweepReference


if t.TYPE_CHECKING:
    from ._detector import DetectorConfig

_MIN_LEAKAGE_FREE_DIST_M = {
    a121.Profile.PROFILE_1: 0.12,
    a121.Profile.PROFILE_2: 0.28,
    a121.Profile.PROFILE_3: 0.56,
    a121.Profile.PROFILE_4: 0.76,
    a121.Profile.PROFILE_5: 1.28,
}
_MIN_NUM_POINTS_IN_ENVELOPE_FWHM_SPAN = 4.0
_VALID_STEP_LENGTHS = [1, 2, 3, 4, 6, 8, 12, 24]
_NUM_FAR_RANGE_GROUPS = 2
_NUM_SUBSWEEPS_IN_SENSOR_CONFIG = 4
_MAX_NUM_POINTS_IN_SENSOR_CONFIG = 4095  # what a single buffered sensor config holds
_HWAAS_MIN_DISTANCE = 1.0
_MAX_HWAAS = 511
_MIN_HWAAS = 1
_BREAKPOINT_DENSITY_EXPONENT = 0.65
# A sensor config beyond the first costs a prepare and a measurement start on every update, so
# the far range takes a second one only when its finer HWAAS steps save at least this much
# averaging time
_MIN_SECOND_CONFIG_SAVING_NS = 400_000


class RangeTypes(Flag):
    CLOSE_RANGE = auto()
    TRANSITION_P1 = auto()
    TRANSITION_P3 = auto()
    MAX_PROFILE = auto()

    # Aliases
    ANY_TRANSITION = TRANSITION_P1 | TRANSITION_P3
    FAR_RANGE = TRANSITION_P1 | TRANSITION_P3 | MAX_PROFILE

    @property
    def closest_range_type(self) -> te.Self:
        (closest, *_) = self._masked_in_members
        return closest

    # These features where added in Python 3.11, so can't rely
    # on those yet.
    def __len__(self) -> int:
        """Basically a "bit" count."""
        return len(self._masked_in_members)

    def __iter__(self) -> t.Iterator[te.Self]:
        """Iterate over set "bits"."""
        return iter(self._masked_in_members)

    @property
    def _masked_in_members(self) -> list[te.Self]:
        return [
            mem  # type: ignore[misc]
            for mem in [self.CLOSE_RANGE, self.TRANSITION_P1, self.TRANSITION_P3, self.MAX_PROFILE]
            if bool(self & mem)  # type: ignore[operator]
        ]


def _clamp(value: float, min_val: float, max_val: float) -> float:
    return min(max(value, min_val), max_val)


def _range_overlap(a: tuple[float, float], b: tuple[float, float]) -> t.Optional[float]:
    (a_start, a_end) = sorted(a)
    (b_start, b_end) = sorted(b)
    overlap_start = _clamp(a_start, b_start, b_end)
    overlap_end = _clamp(a_end, b_start, b_end)
    if b_start == b_end:
        # A single point lies in the range it starts, so it lies in exactly one of two
        # ranges that meet at it.
        ranges_overlapping = a_start <= b_start < a_end
    else:
        ranges_overlapping = not (a_start >= b_end or b_start >= a_end)
    return abs(overlap_end - overlap_start) if ranges_overlapping else None


def _calc_hwaas(
    profile: a121.Profile,
    step_length: int,
    distance_m: float,
    signal_quality: float,
    reflector_shape_exponent: float,
) -> int:
    rlg_per_hwaas = RLG_PER_HWAAS_MAP[profile]

    processing_gain = calc_processing_gain(profile, step_length)
    subsweep_end_point_m = max(distance_m, _HWAAS_MIN_DISTANCE)
    rlg = (
        signal_quality
        + reflector_shape_exponent * 10 * np.log10(subsweep_end_point_m)
        - 10 * np.log10(processing_gain)
    )
    hwaas = int(round(10 ** ((rlg - rlg_per_hwaas) / 10)))
    if hwaas < _MIN_HWAAS:
        return _MIN_HWAAS
    elif hwaas > _MAX_HWAAS:
        return _MAX_HWAAS
    else:
        return hwaas


def _calc_hwaas_saturation_m(
    profile: a121.Profile,
    step_length: int,
    signal_quality: float,
    reflector_shape_exponent: float,
) -> float:
    """The distance at which _calc_hwaas's HWAAS curve reaches _MAX_HWAAS.

    Analytic inverse of _calc_hwaas: solves the same RLG-vs-HWAAS relation for
    distance_m instead of for hwaas. Keep the two in sync when editing either one.
    """
    rlg_per_hwaas = RLG_PER_HWAAS_MAP[profile]
    processing_gain = calc_processing_gain(profile, step_length)
    saturation_m = (
        _MAX_HWAAS
        / (10 ** ((signal_quality - 10 * np.log10(processing_gain) - rlg_per_hwaas) / 10))
    ) ** (1 / reflector_shape_exponent)
    return float(saturation_m)


def _calc_max_profile_breakpoints_m(
    start_m: float,
    end_m: float,
    num_breakpoints: int,
    profile: a121.Profile,
    step_length: int,
    signal_quality: float,
    reflector_shape_exponent: float,
) -> list[float]:
    """Power-law-spaced breakpoints for max-profile subsweeps.

    Anchors the spacing to _calc_hwaas_saturation_m so subsweeps are denser before
    hwaas saturates and coarser after, pulling the last breakpoint to end_m. Falls back
    to spacing across the full range when the saturation point isn't inside it.
    """
    u = np.linspace(0, 1, num_breakpoints)
    hwaas_saturation_point_m = _calc_hwaas_saturation_m(
        profile, step_length, signal_quality, reflector_shape_exponent
    )
    breakpoints_m: list[float]
    if start_m < hwaas_saturation_point_m <= end_m:
        breakpoints_m = (
            start_m + (hwaas_saturation_point_m - start_m) * (u**_BREAKPOINT_DENSITY_EXPONENT)
        ).tolist()
        breakpoints_m[-1] = end_m
    else:
        breakpoints_m = (start_m + (end_m - start_m) * (u**_BREAKPOINT_DENSITY_EXPONENT)).tolist()
    return breakpoints_m


def _merge_equal_hwaas(
    breakpoints: list[int],
    hwaas_at: t.Callable[[int], int],
    fits: t.Callable[[list[int]], bool],
) -> list[int]:
    """Drop the boundaries between max profile subsweeps that share HWAAS.

    Such a boundary splits a span the sensor measures the same way either side
    of it, which costs a subsweep, and eventually a sensor config, for nothing.
    Only the max profile is merged: the transitions carry a profile and a step
    length of their own, so they stay whatever their HWAAS comes out as.

    A boundary also stays where the breakpoints without it do not ``fit``, since
    a merge shifts subsweeps between sensor configs and can overfill one.
    """
    kept = list(breakpoints)
    i = 1

    while i < len(kept) - 1:
        candidate = kept[:i] + kept[i + 1 :]

        if hwaas_at(kept[i]) == hwaas_at(kept[i + 1]) and fits(candidate):
            kept = candidate
        else:
            i += 1

    return kept


def _max_profile_layout(
    breakpoints: list[int], margins: tuple[int, int], step_length: int
) -> list[tuple[int, int]]:
    """Start point and number of points of each max profile subsweep, margins included."""
    spans = [[start, end] for start, end in zip(breakpoints[:-1], breakpoints[1:])]

    if spans:
        spans[0][0] -= margins[0]
        spans[-1][1] += margins[1]

    return [(start, int((end - start) / step_length)) for start, end in spans]


def _max_profile_subsweeps(
    config: DetectorConfig,
    start_m: float,
    end_m: float,
    step_length: int,
    margins: tuple[int, int],
    preceding_num_points: list[int],
    num_subsweeps: int,
) -> list[tuple[int, int, int]]:
    """Start point, number of points and HWAAS of at most num_subsweeps max profile subsweeps."""
    breakpoints_m = _calc_max_profile_breakpoints_m(
        start_m,
        end_m,
        num_subsweeps + 1,
        config.max_profile,
        step_length,
        config.signal_quality,
        config.reflector_shape.exponent,
    )
    breakpoints = remove_dup([_m_to_point(start_m, bp, step_length) for bp in breakpoints_m])

    def hwaas_at(point: int) -> int:
        return _calc_hwaas(
            config.max_profile,
            step_length,
            point * APPROX_BASE_STEP_LENGTH_M,
            config.signal_quality,
            config.reflector_shape.exponent,
        )

    breakpoints = _merge_equal_hwaas(
        breakpoints,
        hwaas_at,
        lambda candidate: _fits_sensor_configs(
            preceding_num_points
            + [n for _, n in _max_profile_layout(candidate, margins, step_length)]
        ),
    )
    return [
        (start_point, num_points, hwaas_at(marginless_end_point))
        for (start_point, num_points), marginless_end_point in zip(
            _max_profile_layout(breakpoints, margins, step_length), breakpoints[1:]
        )
    ]


def _num_averaged_samples(spans: list[tuple[int, int, int]]) -> int:
    """Samples the subsweeps measure, over all their points and HWAAS."""
    return sum(num_points * hwaas for _, num_points, hwaas in spans)


def _fits_sensor_configs(num_points: list[int]) -> bool:
    """Whether far range subsweeps with these numbers of points fit their sensor configs."""
    return all(
        sum(num_points[i : i + _NUM_SUBSWEEPS_IN_SENSOR_CONFIG])
        <= _MAX_NUM_POINTS_IN_SENSOR_CONFIG
        for i in range(0, len(num_points), _NUM_SUBSWEEPS_IN_SENSOR_CONFIG)
    )


def _get_range_types(config: DetectorConfig) -> RangeTypes:
    min_dist_m = _calc_leakage_free_min_dist(config)
    configured_range = (config.start_m, config.end_m)

    range_types = RangeTypes(0)

    measuring_in_direct_leakage = config.start_m < min_dist_m[a121.Profile.PROFILE_1]
    if measuring_in_direct_leakage:
        if config.close_range_leakage_cancellation:
            range_types |= RangeTypes.CLOSE_RANGE
        elif config.max_profile is a121.Profile.PROFILE_1:
            range_types |= RangeTypes.MAX_PROFILE
        else:
            range_types |= RangeTypes.TRANSITION_P1

    if config.max_profile.value > a121.Profile.PROFILE_1.value:
        bounding_profile = min(a121.Profile.PROFILE_3, config.max_profile, key=lambda p: p.value)
        transition_p1_range = (min_dist_m[a121.Profile.PROFILE_1], min_dist_m[bounding_profile])

        step_length_m = (
            _limit_step_length(a121.Profile.PROFILE_1, config.max_step_length)
            * APPROX_BASE_STEP_LENGTH_M
        )

        min_overlap = min(step_length_m, config.end_m - config.start_m)
        range_overlap = _range_overlap(transition_p1_range, configured_range)

        if range_overlap is not None and range_overlap >= min_overlap:
            range_types |= RangeTypes.TRANSITION_P1

    if config.max_profile.value > a121.Profile.PROFILE_3.value:
        transition_p3_range = (min_dist_m[a121.Profile.PROFILE_3], min_dist_m[config.max_profile])

        step_length_m = (
            _limit_step_length(a121.Profile.PROFILE_3, config.max_step_length)
            * APPROX_BASE_STEP_LENGTH_M
        )

        min_overlap = min(step_length_m, config.end_m - config.start_m)
        range_overlap = _range_overlap(transition_p3_range, configured_range)

        if range_overlap is not None and range_overlap >= min_overlap:
            range_types |= RangeTypes.TRANSITION_P3

    # Also when the range is the single point where max_profile becomes leakage free
    max_profile_min_dist_m = min_dist_m[config.max_profile]
    if max_profile_min_dist_m < config.end_m or (
        config.start_m == config.end_m == max_profile_min_dist_m
    ):
        range_types |= RangeTypes.MAX_PROFILE

    return range_types


def _cfar_margins(profile: a121.Profile, step_length: int) -> int:
    cfar_margin = CfarThreshold.calc_margin(profile, step_length) * step_length
    return cfar_margin


def _close_range_margins(step_length: int, range_types: RangeTypes) -> tuple[int, int]:
    filter_margin_p = (
        get_distance_filter_edge_margin(a121.Profile.PROFILE_1, step_length) * step_length
    )
    left_margin = filter_margin_p

    if range_types & RangeTypes.ANY_TRANSITION:
        right_margin = 2 * filter_margin_p
    else:
        right_margin = filter_margin_p

    return (left_margin, right_margin)


def _transition_p1_margins(step_length: int, range_types: RangeTypes) -> tuple[int, int]:
    filter_margin_p = (
        get_distance_filter_edge_margin(a121.Profile.PROFILE_1, step_length) * step_length
    )
    right_margin = filter_margin_p

    if range_types & RangeTypes.CLOSE_RANGE:
        left_margin = 2 * filter_margin_p
    else:
        left_margin = filter_margin_p

    return (left_margin, right_margin)


def _transition_p3_margins(step_length: int, range_types: RangeTypes) -> tuple[int, int]:
    filter_margin_p = (
        get_distance_filter_edge_margin(a121.Profile.PROFILE_3, step_length) * step_length
    )
    right_margin = filter_margin_p

    if range_types & (RangeTypes.TRANSITION_P1 | RangeTypes.CLOSE_RANGE):
        left_margin = 2 * filter_margin_p
    else:
        left_margin = filter_margin_p

    return (left_margin, right_margin)


def _max_profile_margins(
    step_length: int,
    max_profile: a121.Profile,
    range_types: RangeTypes,
) -> tuple[int, int]:
    filter_margin_p = get_distance_filter_edge_margin(max_profile, step_length) * step_length
    right_margin = filter_margin_p

    if range_types & ~RangeTypes.MAX_PROFILE:
        left_margin = 2 * filter_margin_p
    else:
        left_margin = filter_margin_p

    return (left_margin, right_margin)


def _iter_subsweeps(start_group: int, total: int) -> Iterator[SubsweepReference]:
    for n in range(total):
        yield SubsweepReference(
            group_index=start_group + n // _NUM_SUBSWEEPS_IN_SENSOR_CONFIG,
            subsweep_index=n % _NUM_SUBSWEEPS_IN_SENSOR_CONFIG,
        )


def detector_config_to_processor_specs(
    config: DetectorConfig,
    num_far_subsweeps: int,
) -> list[ProcessorSpec]:
    max_num_far_subsweeps = _NUM_FAR_RANGE_GROUPS * _NUM_SUBSWEEPS_IN_SENSOR_CONFIG
    if num_far_subsweeps > max_num_far_subsweeps or num_far_subsweeps < 0:
        raise ValueError

    far_range_processor_config = ProcessorConfig(
        threshold_method=config.threshold_method,
        fixed_threshold_value=config.fixed_threshold_value,
        fixed_strength_threshold_value=config.fixed_strength_threshold_value,
        threshold_sensitivity=config.threshold_sensitivity,
        reflector_shape=config.reflector_shape,
    )
    close_range_processor_config = ProcessorConfig(
        measurement_type=MeasurementType.CLOSE_RANGE,
        threshold_sensitivity=config.threshold_sensitivity,
        reflector_shape=config.reflector_shape,
    )

    range_types = _get_range_types(config)
    processor_specs = []
    if range_types & RangeTypes.CLOSE_RANGE:
        cr_proc_spec = ProcessorSpec(processor_config=close_range_processor_config)
        processor_specs.append(cr_proc_spec)

    # Iterator of available subsweep references. Will be consumed
    # in the for-loop below.
    far_group_idx = 1 if RangeTypes.CLOSE_RANGE in range_types else 0
    far_subsweep_ref_iter = _iter_subsweeps(far_group_idx, num_far_subsweeps)

    for range_type in range_types & RangeTypes.FAR_RANGE:
        if range_type & RangeTypes.ANY_TRANSITION:
            # If "Transition": Use a single subsweep
            transition_subsweep_ref = next(far_subsweep_ref_iter)

            transition_proc_spec = ProcessorSpec(
                processor_config=far_range_processor_config,
                subsweep_references=[transition_subsweep_ref],
            )

            processor_specs.append(transition_proc_spec)
        elif range_type & RangeTypes.MAX_PROFILE:
            # If "Max Profile": Use the rest of the available subsweeps
            max_profile_subsweep_refs = list(far_subsweep_ref_iter)

            max_profile_proc_spec = ProcessorSpec(
                processor_config=far_range_processor_config,
                subsweep_references=max_profile_subsweep_refs,
            )

            processor_specs.append(max_profile_proc_spec)

    return processor_specs


def carry_over_signal_quality(config: DetectorConfig) -> DetectorConfig:
    """Raise signal quality so a config keeps the HWAAS it had before the gain fix.

    Older versions used a tenth of the matched filter's processing gain in the
    HWAAS calculation. Call this once on a configuration carried over from such a
    version to keep the HWAAS, and the detection performance, of the subsweeps that
    reach furthest. Those use max profile, unless the range ends before it is used.

    :param config: The configuration to carry over. It is left untouched.
    :returns: A copy with signal quality raised by 9*log10(processing gain) of the
        subsweep that reaches furthest.
    """
    (_, profile) = _get_furthest_measurement(config)
    step_length = _limit_step_length(profile, config.max_step_length)
    offset = 9 * np.log10(calc_processing_gain(profile, step_length))
    return attrs.evolve(config, signal_quality=config.signal_quality + float(offset))


def detector_config_to_session_config(
    config: DetectorConfig,
    sensor_ids: list[int],
) -> a121.SessionConfig:
    groups = []

    range_types = _get_range_types(config)
    prf = _get_max_prf(config)

    min_dist_m = _calc_leakage_free_min_dist(config)

    # CLOSE RANGE
    if RangeTypes.CLOSE_RANGE & range_types:
        start_m = config.start_m
        end_m = min(config.end_m, min_dist_m[a121.Profile.PROFILE_1])

        step_length = _limit_step_length(a121.Profile.PROFILE_1, config.max_step_length)
        (left_filter_margin, right_filter_margin) = _close_range_margins(step_length, range_types)
        marginless_end_point = _m_to_point(start_m, end_m, step_length)
        end_point = marginless_end_point + right_filter_margin
        hwaas = _calc_hwaas(
            a121.Profile.PROFILE_1,
            step_length,
            end_point * APPROX_BASE_STEP_LENGTH_M,
            config.signal_quality,
            config.reflector_shape.exponent,
        )
        marginless_start_point = _m_to_point(
            config.start_m,
            config.start_m,
            step_length,
        )
        start_point = marginless_start_point - left_filter_margin
        num_points = int((end_point - start_point) / step_length)

        loopback_subsweep = a121.SubsweepConfig(
            start_point=0,
            num_points=1,
            step_length=1,
            profile=a121.Profile.PROFILE_4,
            hwaas=hwaas,
            receiver_gain=15,
            phase_enhancement=True,
            iq_imbalance_compensation=True,
            enable_loopback=True,
            prf=a121.PRF.PRF_15_6_MHz,
        )

        close_range_subsweep = a121.SubsweepConfig(
            start_point=start_point,
            num_points=num_points,
            step_length=step_length,
            profile=a121.Profile.PROFILE_1,
            hwaas=hwaas,
            receiver_gain=5,
            phase_enhancement=True,
            iq_imbalance_compensation=True,
            prf=a121.PRF.PRF_15_6_MHz,
        )
        sensor_config = a121.SensorConfig(
            subsweeps=[loopback_subsweep, close_range_subsweep],
            sweeps_per_frame=10,
        )

        groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})

    # TRANSITION
    far_subsweeps = []

    if range_types & RangeTypes.TRANSITION_P1:
        bounding_profile = min(a121.Profile.PROFILE_3, config.max_profile, key=lambda p: p.value)

        if range_types.closest_range_type is RangeTypes.TRANSITION_P1:
            start_m = config.start_m
        else:
            start_m = max(config.start_m, min_dist_m[a121.Profile.PROFILE_1])

        end_m = min(config.end_m, min_dist_m[bounding_profile])
        step_length = _limit_step_length(a121.Profile.PROFILE_1, config.max_step_length)

        (left_filter_margin, right_filter_margin) = _transition_p1_margins(
            step_length, range_types
        )

        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(a121.Profile.PROFILE_1, step_length)
        else:
            cfar_margin = 0

        marginless_start_point = _m_to_point(start_m, start_m, step_length)
        marginless_end_point = _m_to_point(start_m, end_m, step_length)

        if marginless_start_point == marginless_end_point:
            marginless_end_point += step_length

        start_point = marginless_start_point - left_filter_margin - cfar_margin
        end_point = marginless_end_point + right_filter_margin + cfar_margin
        num_points = int((end_point - start_point) / step_length)

        hwaas = _calc_hwaas(
            a121.Profile.PROFILE_1,
            step_length,
            marginless_end_point * APPROX_BASE_STEP_LENGTH_M,
            config.signal_quality,
            config.reflector_shape.exponent,
        )

        far_subsweeps.append(
            a121.SubsweepConfig(
                start_point=start_point,
                num_points=num_points,
                step_length=step_length,
                profile=a121.Profile.PROFILE_1,
                hwaas=hwaas,
                receiver_gain=10,
                phase_enhancement=True,
                iq_imbalance_compensation=True,
                prf=prf,
            )
        )

    if range_types & RangeTypes.TRANSITION_P3:
        start_m = max(config.start_m, min_dist_m[a121.Profile.PROFILE_3])
        end_m = min(config.end_m, min_dist_m[config.max_profile])
        step_length = _limit_step_length(a121.Profile.PROFILE_3, config.max_step_length)

        (left_filter_margin, right_filter_margin) = _transition_p3_margins(
            step_length,
            range_types,
        )
        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(a121.Profile.PROFILE_3, step_length)
        else:
            cfar_margin = 0

        marginless_start_point = _m_to_point(start_m, start_m, step_length)
        marginless_end_point = _m_to_point(start_m, end_m, step_length)

        if marginless_start_point == marginless_end_point:
            marginless_end_point += step_length

        start_point = marginless_start_point - left_filter_margin - cfar_margin
        end_point = marginless_end_point + right_filter_margin + cfar_margin
        num_points = int((end_point - start_point) / step_length)

        hwaas = _calc_hwaas(
            a121.Profile.PROFILE_3,
            step_length,
            marginless_end_point * APPROX_BASE_STEP_LENGTH_M,
            config.signal_quality,
            config.reflector_shape.exponent,
        )

        far_subsweeps.append(
            a121.SubsweepConfig(
                start_point=start_point,
                num_points=num_points,
                step_length=step_length,
                profile=a121.Profile.PROFILE_3,
                hwaas=hwaas,
                receiver_gain=10,
                phase_enhancement=True,
                iq_imbalance_compensation=True,
                prf=prf,
            )
        )

    # Max Profile
    if range_types & RangeTypes.MAX_PROFILE:
        if range_types.closest_range_type is RangeTypes.MAX_PROFILE:
            start_m = config.start_m
        else:
            start_m = max(config.start_m, min_dist_m[config.max_profile])

        end_m = config.end_m
        step_length = _limit_step_length(config.max_profile, config.max_step_length)

        (left_filter_margin, right_filter_margin) = _max_profile_margins(
            step_length, config.max_profile, range_types
        )
        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(config.max_profile, step_length)
        else:
            cfar_margin = 0

        num_transitions = len(range_types & RangeTypes.ANY_TRANSITION)
        margins = (left_filter_margin + cfar_margin, right_filter_margin + cfar_margin)
        preceding_num_points = [subsweep.num_points for subsweep in far_subsweeps]

        def layout(num_subsweeps: int) -> list[tuple[int, int, int]]:
            return _max_profile_subsweeps(
                config,
                start_m,
                end_m,
                step_length,
                margins,
                preceding_num_points,
                num_subsweeps,
            )

        spans = layout(_NUM_FAR_RANGE_GROUPS * _NUM_SUBSWEEPS_IN_SENSOR_CONFIG - num_transitions)
        if num_transitions + len(spans) > _NUM_SUBSWEEPS_IN_SENSOR_CONFIG:
            one_config = layout(_NUM_SUBSWEEPS_IN_SENSOR_CONFIG - num_transitions)
            saved_samples = _num_averaged_samples(one_config) - _num_averaged_samples(spans)
            # the table holds whole nanoseconds, so this compares exactly, as in C
            sample_ns = round(a121.get_sample_duration(prf, config.max_profile) * 1e9)
            if (
                _fits_sensor_configs(preceding_num_points + [n for _, n, _ in one_config])
                and saved_samples * sample_ns < _MIN_SECOND_CONFIG_SAVING_NS
            ):
                spans = one_config

        for start_point, num_points, hwaas in spans:
            far_subsweeps.append(
                a121.SubsweepConfig(
                    start_point=start_point,
                    num_points=num_points,
                    step_length=step_length,
                    profile=config.max_profile,
                    hwaas=hwaas,
                    receiver_gain=10,
                    phase_enhancement=True,
                    iq_imbalance_compensation=True,
                    prf=prf,
                )
            )

    if len(far_subsweeps) > 0:
        grouped_subsweeps = [
            far_subsweeps[i : i + _NUM_SUBSWEEPS_IN_SENSOR_CONFIG]
            for i in range(0, len(far_subsweeps), _NUM_SUBSWEEPS_IN_SENSOR_CONFIG)
        ]
        for subsweep_group in grouped_subsweeps:
            sensor_config = a121.SensorConfig(subsweeps=subsweep_group, sweeps_per_frame=1)
            groups.append({sensor_id: sensor_config for sensor_id in sensor_ids})

    return a121.SessionConfig(groups, extended=True, update_rate=config.update_rate)


def get_num_far_subsweeps(
    session_config: a121.SessionConfig,
    config: DetectorConfig,
) -> int:
    range_types = _get_range_types(config)
    start_group = 1 if (RangeTypes.CLOSE_RANGE & range_types) else 0
    num_far_subsweeps = 0
    for group in session_config.groups[start_group:]:
        sensor_config = next(iter(group.values()))  # Same config for each sensor. Grab first one.
        num_far_subsweeps += sensor_config.num_subsweeps
    return num_far_subsweeps


def _get_furthest_measurement(config: DetectorConfig) -> tuple[float, a121.Profile]:
    range_types = _get_range_types(config)

    if RangeTypes.MAX_PROFILE in range_types:
        step_length = _limit_step_length(config.max_profile, config.max_step_length)

        (_, right_filter_margin) = _max_profile_margins(
            step_length, config.max_profile, range_types
        )

        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(config.max_profile, step_length)
        else:
            cfar_margin = 0

        distance_m = config.end_m + (right_filter_margin + cfar_margin) * APPROX_BASE_STEP_LENGTH_M
        return (
            distance_m,
            config.max_profile,
        )

    if RangeTypes.TRANSITION_P3 in range_types:
        step_length = _limit_step_length(a121.Profile.PROFILE_3, config.max_step_length)

        (_, right_filter_margin) = _transition_p3_margins(step_length, range_types)

        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(a121.Profile.PROFILE_3, step_length)
        else:
            cfar_margin = 0

        distance_m = config.end_m + (right_filter_margin + cfar_margin) * APPROX_BASE_STEP_LENGTH_M
        return (
            distance_m,
            a121.Profile.PROFILE_3,
        )

    if RangeTypes.TRANSITION_P1 in range_types:
        step_length = _limit_step_length(a121.Profile.PROFILE_1, config.max_step_length)

        (_, right_filter_margin) = _transition_p1_margins(step_length, range_types)

        if config.threshold_method is ThresholdMethod.CFAR:
            cfar_margin = _cfar_margins(a121.Profile.PROFILE_1, step_length)
        else:
            cfar_margin = 0

        distance_m = config.end_m + (right_filter_margin + cfar_margin) * APPROX_BASE_STEP_LENGTH_M
        return (
            distance_m,
            a121.Profile.PROFILE_1,
        )

    if RangeTypes.CLOSE_RANGE in range_types:
        step_length = _limit_step_length(a121.Profile.PROFILE_1, config.max_step_length)
        (_, right_filter_margin) = _close_range_margins(step_length, range_types)

        distance_m = config.end_m + (right_filter_margin * APPROX_BASE_STEP_LENGTH_M)
        return (
            distance_m,
            a121.Profile.PROFILE_1,
        )

    msg = "Unreachable"
    raise Exception(msg)


def _get_max_prf(config: DetectorConfig) -> a121.PRF:
    (distance_m, profile) = _get_furthest_measurement(config)
    prf = select_prf_m(distance_m, profile)
    return prf


def _m_to_point(start_m: float, distance_m: float, step_length: int) -> int:
    start_p = int(round(start_m / APPROX_BASE_STEP_LENGTH_M))
    point_frac = (distance_m - start_m) / APPROX_BASE_STEP_LENGTH_M + start_p
    return (round(point_frac) // step_length) * step_length


def remove_dup(breakpoints: list[int]) -> list[int]:
    unique_bps = sorted(set(breakpoints[1:]))

    unique_bps = [breakpoints[0]] + unique_bps

    return unique_bps


def _calc_leakage_free_min_dist(config: DetectorConfig) -> dict[a121.Profile, float]:
    """This function calculates the shortest leakage free distance per profile, for all profiles
    up to max_profile"""
    min_dist_m = {}
    for profile, min_dist in _MIN_LEAKAGE_FREE_DIST_M.items():
        min_dist_m[profile] = min_dist
        if config.threshold_method == ThresholdMethod.CFAR:
            step_length = _limit_step_length(profile, config.max_step_length)
            cfar_margin_m = (
                CfarThreshold.calc_margin(profile, step_length)
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
