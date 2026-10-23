# Copyright (c) Acconeer AB, 2026
# All rights reserved
"""Dynamic-HWAAS subsweep layout covering a required per-point HWAAS curve at
minimal estimated power.

Steps of :func:`solve_subsweep_layout`:

1. :func:`_candidate_boundaries`: positions a segment boundary may sit at.
2. :func:`_segment_cost_tables`: per candidate segment, the cheapest exponent,
   its smallest covering ``hwaas_max``, and its cost.
3. :func:`_optimal_layouts_by_k`: the cheapest layout per segment count K.
4. :func:`_realize_layout`: ``SubsweepConfig``\\ s whose quantized HWAAS
   covers the curve.
5. :func:`_cheapest_layout`: the realized layout with the lowest :func:`_score`.

A segment delivers ``hwaas(n) = max(hwaas_min, hwaas_max * (d_n / d_end) ** exponent)``,
monotonic in ``hwaas_max``, so a segment's smallest covering ``hwaas_max`` is
a closed-form range max. The exponent affects only its own segment's cost and
is chosen per segment; the breakpoints are chosen by an exact dynamic program
(DP).

Cost is sample time: HWAAS summed over a segment's points, divided by the
segment's PRF. The DP sums the ideal,
unquantized HWAAS; :func:`_score` sums the realized ``hwaas_points``.
"""

from __future__ import annotations

from collections.abc import Callable

import attrs
import numpy as np
import numpy.typing as npt

from acconeer.exptool import a2
from acconeer.exptool.a2._core.entities.configs.subsweep_config import (
    MAX_HWAAS,
    MAX_HWAAS_EXPONENT,
    MAX_RX_ANTENNA_MASK,
    MAX_TX_ANTENNA_MASK,
    MIN_HWAAS,
    MIN_HWAAS_EXPONENT,
)
from acconeer.exptool.a2.algo._utils import get_distances, get_prf_for_end_m


_HWAAS_EXPONENT_CHOICES: tuple[int, ...] = tuple(range(MIN_HWAAS_EXPONENT, MAX_HWAAS_EXPONENT + 1))
_MAX_BREAKPOINT_CANDIDATES = 200


@attrs.define(frozen=True)
class _Segment:
    """One subsweep of a layout, in point indices: ``[start_idx, end_idx)``."""

    start_idx: int
    end_idx: int
    exponent: int
    hwaas_max: int


def solve_subsweep_layout(
    required_hwaas: npt.NDArray[np.float64],
    *,
    start_point: int,
    profile: a2.Profile,
    step_length: int,
    receiver_gain: int,
    hwaas_min: int = MIN_HWAAS,
    max_num_subsweeps: int = a2.SensorConfig.MAX_NUM_SUBSWEEPS,
    tx_antenna_mask: int = MAX_TX_ANTENNA_MASK,
    rx_antenna_mask: int = MAX_RX_ANTENNA_MASK,
) -> list[a2.SubsweepConfig]:
    """Cheapest subsweep layout whose delivered HWAAS covers ``required_hwaas``.

    All subsweeps share ``profile`` and ``step_length``. Each gets its own
    ``hwaas_max``, ``hwaas_exponent``, and the highest PRF usable with
    ``profile`` whose MMD covers its farthest point.

    Points where ``hwaas_max`` saturates at ``MAX_HWAAS`` may fall below
    ``required_hwaas``; this is not reported here, but as a ``ValidationWarning``
    by the config that calls this.

    :param required_hwaas: Required HWAAS per measured point, from ``start_point``
        in steps of ``step_length``. Values above ``MAX_HWAAS`` are capped to it.
    :param start_point: Start point of the first subsweep. Must be positive.
    :param profile: Profile of every subsweep.
    :param step_length: Step length of every subsweep.
    :param receiver_gain: Receiver gain of every subsweep.
    :param hwaas_min: ``hwaas_min`` of every subsweep.
    :param max_num_subsweeps: Upper bound on the number of subsweeps.
    :param tx_antenna_mask: TX antenna mask of every subsweep.
    :param rx_antenna_mask: RX antenna mask of every subsweep.
    :returns: The subsweeps, in point order, together covering every point.
    :raises ValueError: If ``start_point <= 0``, no layout is feasible, or the
        farthest point lies beyond the MMD of the lowest PRF.
    """
    if start_point <= 0:
        # SubsweepConfig gives points at d_n <= 0 only hwaas_min, whatever the
        # exponent, which the cost model does not represent.
        msg = f"start_point must be positive, got {start_point}."
        raise ValueError(msg)

    capped_hwaas = np.minimum(required_hwaas, MAX_HWAAS)
    num_points = len(capped_hwaas)
    distances_m = get_distances(start_point, step_length, num_points)
    max_k = min(max_num_subsweeps, num_points)

    boundaries = _candidate_boundaries(num_points)
    costs = _segment_cost_tables(distances_m, capped_hwaas, boundaries, hwaas_min, profile)
    layouts_by_k = _optimal_layouts_by_k(costs, boundaries, max_k)

    def to_subsweep(segment: _Segment) -> a2.SubsweepConfig:
        return _segment_to_subsweep(
            segment,
            distances_m=distances_m,
            start_point=start_point,
            step_length=step_length,
            profile=profile,
            receiver_gain=receiver_gain,
            hwaas_min=hwaas_min,
            tx_antenna_mask=tx_antenna_mask,
            rx_antenna_mask=rx_antenna_mask,
        )

    candidates_by_k = {
        k: _realize_layout(segments, capped_hwaas, to_subsweep)
        for k, segments in layouts_by_k.items()
    }
    return _cheapest_layout(candidates_by_k)


# --- Step 1: candidate boundaries ---------------------------------------------


def _candidate_boundaries(num_points: int) -> npt.NDArray[np.int_]:
    """Positions in ``[0, num_points]`` a segment boundary may sit at.

    Always includes 0 and ``num_points``; at most ``_MAX_BREAKPOINT_CANDIDATES``
    evenly spaced positions.
    """
    if num_points <= _MAX_BREAKPOINT_CANDIDATES:
        return np.arange(num_points + 1)
    positions = np.round(np.linspace(0, num_points, _MAX_BREAKPOINT_CANDIDATES)).astype(int)
    unique_positions: npt.NDArray[np.int_] = np.unique(positions)
    return unique_positions


# --- Step 2: per-segment cost tables ------------------------------------------


@attrs.define(frozen=True)
class _SegmentCosts:
    """Per candidate segment ``[boundaries[idx_i], boundaries[idx_j])``: its
    cheapest exponent, and that exponent's ``hwaas_max`` and cost.

    Every field has shape ``(m, m)``, indexed ``[idx_i, idx_j]``, and is only
    meaningful where ``idx_i < idx_j``; ``cost`` is ``inf`` elsewhere. The DP
    requires ``cost`` to be additive over a layout's segments.
    """

    exponent: npt.NDArray[np.int_]  # cheapest hwaas_exponent
    hwaas_max: npt.NDArray[np.float64]  # smallest covering hwaas_max for that exponent
    cost: npt.NDArray[np.float64]  # what the DP minimizes


def _segment_cost_tables(
    distances_m: npt.NDArray[np.float64],
    required_hwaas: npt.NDArray[np.float64],
    boundaries: npt.NDArray[np.int_],
    hwaas_min: int,
    profile: a2.Profile,
) -> _SegmentCosts:
    """Cheapest exponent, its ``hwaas_max``, and its ideal sample time, for
    every candidate segment.

    A segment's PRF depends only on its farthest point, i.e. on ``idx_j``, so
    its PRF is a per-column divisor. Exact ties between exponents go
    to the smallest exponent.
    """
    # Column idx_j=0 is never a segment end; clipped only to stay in bounds.
    end_cols = np.clip(boundaries - 1, 0, len(distances_m) - 1)
    prf_hz = np.array(
        [get_prf_for_end_m(float(distances_m[col]), profile=profile).frequency for col in end_cols]
    )

    tables_by_exponent = _exponent_tables(distances_m, required_hwaas)
    hwaas_max_by_exponent = []
    cost_by_exponent = []
    for exponent in _HWAAS_EXPONENT_CHOICES:
        tables = tables_by_exponent[exponent]
        hwaas_max = _hwaas_max_table(distances_m, required_hwaas, boundaries, tables, hwaas_min)
        hwaas_max_by_exponent.append(hwaas_max)
        hwaas_sum = _hwaas_sum_table(
            distances_m, boundaries, tables, hwaas_min, exponent, hwaas_max
        )
        cost_by_exponent.append(hwaas_sum / prf_hz[np.newaxis, :])

    # (m, m, num_exponents); inf where not a segment (nan, idx_i >= idx_j) or
    # where the exponent needs hwaas_max > MAX_HWAAS to cover the segment.
    cost = np.stack(cost_by_exponent, axis=-1)
    hwaas_max = np.stack(hwaas_max_by_exponent, axis=-1)
    cost = np.where(np.isnan(cost) | (hwaas_max > MAX_HWAAS), np.inf, cost)

    best_pos = np.argmin(cost, axis=-1)  # (m, m)
    best = best_pos[..., np.newaxis]
    return _SegmentCosts(
        exponent=np.asarray(_HWAAS_EXPONENT_CHOICES)[best_pos],
        hwaas_max=np.take_along_axis(hwaas_max, best, axis=-1)[..., 0],
        cost=np.take_along_axis(cost, best, axis=-1)[..., 0],
    )


@attrs.define(frozen=True)
class _ExponentTables:
    """Per-point tables for one exponent, for range queries over segments."""

    pow_exp: npt.NDArray[np.float64]  # distances_m ** exponent, shape (N,)
    # shape (N+1,); prefix_sum_pow_exp[k] = sum(pow_exp[:k])
    prefix_sum_pow_exp: npt.NDArray[np.float64]
    key_exp: npt.NDArray[np.float64]  # required_hwaas / pow_exp (-inf where pow_exp == 0)


def _exponent_tables(
    distances_m: npt.NDArray[np.float64], required_hwaas: npt.NDArray[np.float64]
) -> dict[int, _ExponentTables]:
    tables = {}
    for exponent in _HWAAS_EXPONENT_CHOICES:
        pow_exp = distances_m.astype(np.float64) ** exponent
        prefix_sum_pow_exp = np.concatenate([[0.0], np.cumsum(pow_exp)])
        # pow_exp == 0 at distances_m == 0: the point gets only hwaas_min,
        # whatever hwaas_max is, so it must not constrain hwaas_max.
        with np.errstate(divide="ignore", invalid="ignore"):
            key_exp = np.where(pow_exp > 0, required_hwaas / pow_exp, -np.inf)
        tables[exponent] = _ExponentTables(pow_exp, prefix_sum_pow_exp, key_exp)
    return tables


def _hwaas_max_table(
    distances_m: npt.NDArray[np.float64],
    required_hwaas: npt.NDArray[np.float64],
    boundaries: npt.NDArray[np.int_],
    tables: _ExponentTables,
    hwaas_min: int,
) -> npt.NDArray[np.float64]:
    """Smallest covering ``hwaas_max`` per candidate segment, for one exponent.

    ``table[idx_i, idx_j]`` is the smallest ``hwaas_max >= hwaas_min`` for which
    ``max(hwaas_min, hwaas_max * (d_n / d_end) ** exponent)`` reaches
    ``required_hwaas`` on all of ``[boundaries[idx_i], boundaries[idx_j])``;
    ``nan`` where ``idx_i >= idx_j``. Not capped at ``MAX_HWAAS``: a value
    above it means this exponent cannot cover the segment.

    Points with ``required_hwaas <= hwaas_min`` are covered by the floor and
    excluded from the max: dividing them by a small ``d_n ** exponent`` would
    otherwise inflate ``hwaas_max`` for the whole segment.
    """
    m = len(boundaries)
    n = len(distances_m)
    masked_key = np.where(required_hwaas > hwaas_min, tables.key_exp, -np.inf)

    # Row idx_i is -inf before boundaries[idx_i], so its running max spans the segment only.
    started = np.arange(n)[np.newaxis, :] >= boundaries[:, np.newaxis]  # (m, n)
    padded = np.where(started, masked_key[np.newaxis, :], -np.inf)
    cummax = np.maximum.accumulate(padded, axis=1)  # (m, n)

    # Last point of each segment; idx_j=0 is never a segment end, clipped to stay in bounds.
    end_cols = np.clip(boundaries - 1, 0, n - 1)
    seg_max = cummax[:, end_cols]  # (m, m)

    # 0 * -inf -> nan for the point-0 segment; always overridden below.
    with np.errstate(invalid="ignore"):
        needed = tables.pow_exp[end_cols][np.newaxis, :] * seg_max
    hwaas_max = np.maximum(np.ceil(needed), hwaas_min)
    hwaas_max = np.where(np.isneginf(seg_max), float(hwaas_min), hwaas_max)

    idx = np.arange(m)
    valid = idx[:, np.newaxis] < idx[np.newaxis, :]
    return np.where(valid, hwaas_max, np.nan)


def _hwaas_sum_table(
    distances_m: npt.NDArray[np.float64],
    boundaries: npt.NDArray[np.int_],
    tables: _ExponentTables,
    hwaas_min: int,
    exponent: int,
    hwaas_max_table: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """Ideal, unquantized HWAAS summed over each candidate segment, for one exponent.

    ``table[idx_i, idx_j]`` is the sum of
    ``max(hwaas_min, hwaas_max_table[idx_i, idx_j] * (d_n / d_end) ** exponent)``
    over ``[boundaries[idx_i], boundaries[idx_j])``, split at the point where
    the power-law term crosses the ``hwaas_min`` floor; ``nan`` where
    ``idx_i >= idx_j``.

    Cells with ``idx_i >= idx_j`` go through the same arithmetic: their
    ``nan`` ``hwaas_max_table`` propagates without error (``np.searchsorted``
    sorts ``nan`` last, so indices stay in bounds).
    """
    m = len(boundaries)
    idx = np.arange(m)
    valid = idx[:, np.newaxis] < idx[np.newaxis, :]

    i_pos = boundaries[:, np.newaxis]  # (m, 1)
    j_pos = boundaries[np.newaxis, :]  # (1, m)
    seg_len = j_pos - i_pos  # (m, m); meaningful only where valid

    if exponent == 0:
        # (d_n/d_end)^0 == 1 always, so delivered HWAAS is hwaas_max throughout.
        return np.where(valid, hwaas_max_table * seg_len, np.nan)

    end_idx = np.clip(boundaries - 1, 0, len(distances_m) - 1)
    d_end = distances_m[end_idx][np.newaxis, :]  # (1, m)

    # hwaas_max * seg_len is exact when no floor region binds, and for a
    # one-point segment (its only point is its end). One-point segments must
    # use it: the prefix-sum path's rounding noise would break their exact
    # tie between exponents.
    degenerate = (hwaas_max_table <= hwaas_min) | (seg_len == 1)
    safe_hwaas_max = np.maximum(hwaas_max_table, hwaas_min + 1)  # avoid 0-division/negative pow
    threshold_d = d_end * (hwaas_min / safe_hwaas_max) ** (1.0 / exponent)

    # distances_m is ascending, so the split within a segment is the split in
    # the full array minus boundaries[idx_i], clipped to [0, seg_len].
    global_split = np.searchsorted(distances_m, threshold_d, side="right")
    split_offset = np.minimum(np.clip(global_split - i_pos, 0, None), seg_len)

    floor_hwaas_sum = split_offset * hwaas_min
    scaling_sum_pow_exp = (
        tables.prefix_sum_pow_exp[j_pos] - tables.prefix_sum_pow_exp[i_pos + split_offset]
    )
    pow_exp_end = tables.pow_exp[end_idx][np.newaxis, :]  # (1, m)
    # 0 when the segment ends at distances_m == 0; such cells are always `degenerate`.
    with np.errstate(divide="ignore", invalid="ignore"):
        scaling_hwaas_sum = hwaas_max_table / pow_exp_end * scaling_sum_pow_exp

    table = np.where(degenerate, hwaas_max_table * seg_len, floor_hwaas_sum + scaling_hwaas_sum)
    return np.where(valid, table, np.nan)


# --- Step 3: exact DP over segment counts -------------------------------------


@attrs.define(frozen=True)
class _Choice:
    """The DP's winning last segment for a state ``(k, idx_j)``."""

    prev_boundary_idx: int
    exponent: int
    hwaas_max: int


_ChoiceTable = dict[tuple[int, int], _Choice]


def _optimal_layouts_by_k(
    costs: _SegmentCosts, boundaries: npt.NDArray[np.int_], max_k: int
) -> dict[int, list[_Segment]]:
    """Minimum-cost layout covering all points, per feasible segment count.

    :returns: ``k -> segments`` for every feasible ``k`` in ``[1, max_k]``, ascending.
    """
    dp, choice = _dp_forward(costs, max_k)
    last_idx = len(boundaries) - 1
    return {
        k: _backtrack(choice, boundaries, k, last_idx)
        for k in range(1, max_k + 1)
        if np.isfinite(dp[k, last_idx])
    }


def _dp_forward(costs: _SegmentCosts, max_k: int) -> tuple[npt.NDArray[np.float64], _ChoiceTable]:
    """Forward pass of ``dp[k, j] = min over i of dp[k-1, i] + cost[i, j]``.

    Ties go to the smallest ``idx_i``.

    :returns: ``dp[k, idx_j]``, the minimum cost of covering
        ``[0, boundaries[idx_j])`` with exactly ``k`` segments (``inf`` if
        infeasible), and ``choice[(k, idx_j)]``, the last segment achieving it.
    """
    m = costs.cost.shape[0]
    inf = float("inf")
    cost_by_j = costs.cost.T  # (idx_j, idx_i): one row of candidates per idx_j

    dp = np.full((max_k + 1, m), inf)
    dp[0, 0] = 0.0
    choice: _ChoiceTable = {}

    for k in range(1, max_k + 1):
        total_cost = cost_by_j + dp[k - 1][np.newaxis, :]  # (idx_j, idx_i)
        best_idx_i = np.argmin(total_cost, axis=1)
        best_cost = total_cost[np.arange(m), best_idx_i]

        for idx_j in range(1, m):
            cost = best_cost[idx_j]
            if np.isfinite(cost):
                idx_i = int(best_idx_i[idx_j])
                dp[k, idx_j] = cost
                choice[(k, idx_j)] = _Choice(
                    idx_i,
                    int(costs.exponent[idx_i, idx_j]),
                    int(costs.hwaas_max[idx_i, idx_j]),
                )

    return dp, choice


def _backtrack(
    choice: _ChoiceTable, boundaries: npt.NDArray[np.int_], k: int, last_idx: int
) -> list[_Segment]:
    """The ``k`` segments ending at ``last_idx``, in point order and point indices."""
    segments: list[_Segment] = []
    idx_j = last_idx
    for remaining_k in range(k, 0, -1):
        c = choice[(remaining_k, idx_j)]
        segments.append(
            _Segment(boundaries[c.prev_boundary_idx], boundaries[idx_j], c.exponent, c.hwaas_max)
        )
        idx_j = c.prev_boundary_idx
    segments.reverse()
    return segments


# --- Step 4: realize as SubsweepConfigs and verify coverage -------------------


def _realize_layout(
    segments: list[_Segment],
    required_hwaas: npt.NDArray[np.float64],
    to_subsweep: Callable[[_Segment], a2.SubsweepConfig],
) -> list[a2.SubsweepConfig]:
    """Each segment's ``SubsweepConfig``, with ``hwaas_max`` raised until its
    quantized ``hwaas_points`` cover the segment's ``required_hwaas``."""
    return [
        _bump_hwaas_max_for_coverage(
            to_subsweep(segment), required_hwaas[segment.start_idx : segment.end_idx]
        )
        for segment in segments
    ]


def _segment_to_subsweep(
    segment: _Segment,
    *,
    distances_m: npt.NDArray[np.float64],
    start_point: int,
    step_length: int,
    profile: a2.Profile,
    receiver_gain: int,
    hwaas_min: int,
    tx_antenna_mask: int,
    rx_antenna_mask: int,
) -> a2.SubsweepConfig:
    return a2.SubsweepConfig(
        start_point=start_point + step_length * segment.start_idx,
        num_points=segment.end_idx - segment.start_idx,
        step_length=step_length,
        profile=profile,
        prf=get_prf_for_end_m(distances_m[segment.end_idx - 1], profile=profile),
        hwaas_max=segment.hwaas_max,
        hwaas_min=hwaas_min,
        hwaas_exponent=segment.exponent,
        tx_antenna_mask=tx_antenna_mask,
        rx_antenna_mask=rx_antenna_mask,
        receiver_gain=receiver_gain,
        enable_tx=True,
    )


def _bump_hwaas_max_for_coverage(
    subsweep: a2.SubsweepConfig, required_hwaas: npt.NDArray[np.float64], max_bumps: int = 64
) -> a2.SubsweepConfig:
    """``subsweep`` with ``hwaas_max`` raised until ``hwaas_points`` reach
    ``required_hwaas`` at every point.

    ``hwaas_points`` are quantized (at most ``MAX_N_TABLE_ENTRIES``
    log-uniform levels) and can fall below the unquantized curve between
    levels. Returns the last attempt, possibly not covering every point, if
    ``hwaas_max`` saturates at ``MAX_HWAAS``.

    :raises RuntimeError: If ``max_bumps`` bumps pass without covering every point.
    """
    for _ in range(max_bumps):
        if np.all(subsweep.hwaas_points >= required_hwaas):
            return subsweep
        if subsweep.hwaas_max >= MAX_HWAAS:
            return subsweep
        subsweep = attrs.evolve(subsweep, hwaas_max=_next_hwaas_max(subsweep, required_hwaas))
    if np.all(subsweep.hwaas_points >= required_hwaas):
        return subsweep
    msg = f"_bump_hwaas_max_for_coverage did not converge within {max_bumps} bumps."
    raise RuntimeError(msg)


def _next_hwaas_max(subsweep: a2.SubsweepConfig, required_hwaas: npt.NDArray[np.float64]) -> int:
    """``hwaas_max`` scaled by the worst per-point shortfall ratio, at least
    +1, capped at ``MAX_HWAAS``."""
    bump_ratio = float(np.max(required_hwaas / np.maximum(subsweep.hwaas_points, 1)))
    return min(
        MAX_HWAAS, max(subsweep.hwaas_max + 1, int(np.ceil(subsweep.hwaas_max * bump_ratio)))
    )


# --- Step 5: pick the segment count -------------------------------------------


def _cheapest_layout(
    candidates_by_k: dict[int, list[a2.SubsweepConfig]],
) -> list[a2.SubsweepConfig]:
    if not candidates_by_k:
        msg = "No feasible subsweep layout found."
        raise ValueError(msg)
    best_k = min(candidates_by_k, key=lambda k: _score(candidates_by_k[k]))
    return candidates_by_k[best_k]


def _score(subsweeps: list[a2.SubsweepConfig]) -> float:
    """Estimated relative power of a layout: the sample time of its realized
    ``hwaas_points``, summed over subsweeps.

    Must stay the same cost model as :func:`_segment_cost_tables`.
    """
    return sum(
        float(np.sum(subsweep.hwaas_points)) / subsweep.prf.frequency for subsweep in subsweeps
    )
