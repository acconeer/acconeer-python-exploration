# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import numpy as np

import acconeer.exptool.a121 as a121
from acconeer.exptool.a121.algo import (
    APPROX_BASE_STEP_LENGTH_M,
    ENVELOPE_FWHM_M,
    select_prf,
)
from acconeer.exptool.a121.algo._utils import (
    get_max_profile_without_direct_leakage,
    get_max_step_length,
)


MAX_NUM_SUBSWEEPS = 4
FWHM_MARGIN_FACTOR = 2.0
MIN_DIST_M = {
    a121.Profile.PROFILE_1: 0,
    a121.Profile.PROFILE_2: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_2],
    a121.Profile.PROFILE_3: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_3],
    a121.Profile.PROFILE_4: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_4],
    a121.Profile.PROFILE_5: 2 * ENVELOPE_FWHM_M[a121.Profile.PROFILE_5],
}
BREAK_POINTS_MAP = {
    1: (0, 1.0),
    2: (0, 0.74, 1.0),
    3: (0, 0.54, 0.81, 1.0),
    4: (0, 0.47, 0.70, 0.87, 1.0),
}

"""
Functions to select hwaas and profile for different subsweeps.
"""


def _get_hwaas(signal_quality: float, subsweep_end_point_m: float, profile: a121.Profile) -> int:
    RLG_PER_HWAAS_MAP = {
        a121.Profile.PROFILE_1: 11.3,
        a121.Profile.PROFILE_2: 13.7,
        a121.Profile.PROFILE_3: 19.0,
        a121.Profile.PROFILE_4: 20.5,
        a121.Profile.PROFILE_5: 21.6,
    }

    rlg = signal_quality + 4 * 10 * np.log10(subsweep_end_point_m)
    hwaas_in_subsweep = int(round(10 ** ((rlg - RLG_PER_HWAAS_MAP[profile]) / 10)))
    hwaas_in_subsweep = np.clip(hwaas_in_subsweep, 1, 511)

    return hwaas_in_subsweep


def _get_profile_conf(
    min_profile: a121.Profile, max_profile: a121.Profile, n_subsweeps: int
) -> list[a121.Profile]:
    """
    Function to select profiles for subsweeps.
    The function will eliminate profiles according to the "remove_order".
    """
    base = [
        a121.Profile.PROFILE_1,
        a121.Profile.PROFILE_2,
        a121.Profile.PROFILE_3,
        a121.Profile.PROFILE_4,
    ]
    base = base[base.index(min_profile) : base.index(max_profile) + 1]
    remove_order = [a121.Profile.PROFILE_2, a121.Profile.PROFILE_4, a121.Profile.PROFILE_3]
    for elm in remove_order:
        if len(base) <= n_subsweeps:
            return base
        if elm != base[0] and elm in base:
            base.remove(elm)
    return base


def _get_profile_subsweeps(
    start_m: float,
    end_m: float,
    max_n_subsweeps: int,
    signal_quality: float,
    add_final_point: bool,
) -> list[a121.SubsweepConfig]:
    """
    Splits up the subsweeps with different profiles.
    This function only deals with Profile 4 and lower.
    The hwaas will also differ, but is not the driver.
    Adds all points not including end_m (unless start == end, then add one point).
    If add_final_point is true adds an extra point (possibly after end_m).
    """

    if start_m == end_m:
        add_final_point = False
        end_m += 0.01

    min_profile = get_max_profile_without_direct_leakage(start_m)
    max_profile = get_max_profile_without_direct_leakage(end_m)

    if min_profile == a121.Profile.PROFILE_5:
        min_profile = a121.Profile.PROFILE_4
    if max_profile == a121.Profile.PROFILE_5:
        max_profile = a121.Profile.PROFILE_4
    profiles_to_use = _get_profile_conf(min_profile, max_profile, max_n_subsweeps)

    curr_point = start_m
    subsweeps_configs = []

    cut_points = [MIN_DIST_M[profile] for profile in profiles_to_use] + [end_m]

    for profile, cut_point in zip(profiles_to_use, cut_points[1:]):
        curr_start = curr_point
        n_points_in_subsweep = 0
        step = get_max_step_length(profile)
        while curr_point < cut_point:
            curr_point += step * APPROX_BASE_STEP_LENGTH_M
            n_points_in_subsweep += 1
        curr_point_ind = int(round(curr_point / APPROX_BASE_STEP_LENGTH_M))
        subsweeps_configs.append(
            a121.SubsweepConfig(
                profile=profile,
                start_point=int(round(curr_start / APPROX_BASE_STEP_LENGTH_M)),
                step_length=step,
                num_points=n_points_in_subsweep,
                hwaas=_get_hwaas(signal_quality, curr_point, profile),
                prf=select_prf(curr_point_ind, profile),
            )
        )
    if add_final_point:
        subsweeps_configs[-1].num_points += 1
    return subsweeps_configs


def _get_hwaas_subsweeps(
    start_m: float,
    end_m: float,
    max_n_subsweeps: int,
    signal_quality: float,
    add_final_point: bool,
) -> list[a121.SubsweepConfig]:
    """
    Split up the subsweeps with different hwaas (further -> higher hwaas).
    Assumes that all subsweeps uses profile 5.
    Adds all points not including end_m (unless start == end, then add one point).
    If add_final_point is true adds an extra point (possibly after end_m).
    """

    if start_m == end_m:
        add_final_point = False
        end_m += 0.01

    profile = a121.Profile.PROFILE_5
    step = get_max_step_length(profile)
    break_points_fracs = BREAK_POINTS_MAP[max_n_subsweeps]
    cut_points = start_m + np.array(break_points_fracs) * (end_m - start_m)
    curr_point = start_m
    subsweeps_configs = []
    for cut_point in cut_points[1:]:
        n_points_in_subsweep = 0
        curr_start = curr_point
        while curr_point < cut_point:
            curr_point += step * APPROX_BASE_STEP_LENGTH_M
            n_points_in_subsweep += 1
        if n_points_in_subsweep > 0:
            curr_point_ind = int(round(curr_point / APPROX_BASE_STEP_LENGTH_M))
            subsweeps_configs.append(
                a121.SubsweepConfig(
                    profile=profile,
                    start_point=int(round(curr_start / APPROX_BASE_STEP_LENGTH_M)),
                    step_length=step,
                    num_points=n_points_in_subsweep,
                    hwaas=_get_hwaas(signal_quality, curr_point, profile),
                    prf=select_prf(curr_point_ind, profile),
                )
            )
    if add_final_point:
        subsweeps_configs[-1].num_points += 1
    return subsweeps_configs


def get_subsweep_configs(
    start_m: float, end_m: float, signal_quality: float
) -> list[a121.SubsweepConfig]:
    """
    The function separates on two cases, closer than profile 5 and further than profile 5.
    The main driver for the close case will be to use different profiles for the subsweeps.
    For the far case, all subsweeps will use profile 5 and instead have different hwaas.
    If both cases is applicable, a split will occur.
    For each 64 cm another subsweep will be added to the "far" case up to three subsweeps.
    """

    # clip to closest multiple of APPROX_BASE_STEP_LENGTH_M
    start_m = np.ceil(start_m / APPROX_BASE_STEP_LENGTH_M) * APPROX_BASE_STEP_LENGTH_M

    end_m = np.ceil(end_m / APPROX_BASE_STEP_LENGTH_M) * APPROX_BASE_STEP_LENGTH_M

    profile_5_breakpoint = MIN_DIST_M[a121.Profile.PROFILE_5]

    if end_m < profile_5_breakpoint:
        ss = _get_profile_subsweeps(start_m, end_m, 4, signal_quality, add_final_point=True)
    elif start_m >= profile_5_breakpoint:
        ss = _get_hwaas_subsweeps(start_m, end_m, 4, signal_quality, add_final_point=True)
    else:
        n_hwaas_subs = max(min(3, int(round(np.ceil(end_m / profile_5_breakpoint))) - 1), 1)
        n_profile_subs = 4 - n_hwaas_subs
        ss_1 = _get_profile_subsweeps(
            start_m, profile_5_breakpoint, n_profile_subs, signal_quality, add_final_point=False
        )
        ss_2 = _get_hwaas_subsweeps(
            profile_5_breakpoint, end_m, n_hwaas_subs, signal_quality, add_final_point=True
        )
        ss = ss_1 + ss_2
    return ss
