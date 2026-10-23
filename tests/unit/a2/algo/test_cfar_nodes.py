# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for CFAR1DThresholdNode and CFAR2DThresholdNode.

Both nodes compute a per-cell detection threshold from a local noise estimate
formed over a CFAR reference window split into arms around a guard band. The
threshold scales as ``noise * N * (fpr^(-1/N) - 1)`` where ``N`` is the number
of reference cells actually used.

Test groups:

1. Constructor validation — guards on ``theoretical_fpr`` and
   ``side_lobe_compensation_dB`` fire for out-of-range values.
2. Input validation — wrong ``ndim`` on the data array.
3. Constant noise floor — for a uniform input the noise estimate equals the
   floor, so the threshold reduces to the closed-form CFAR scaling factor at
   any interior cell. Verifies the core formula.
4. 1D aggregate methods — CA / SO / GO on an input with high noise on one
   side and low noise on the other; checks which arm is selected.
5. 2D aggregate methods — parameterized over all 11 variants on a 2D map with
   independently controllable arms; checks per-variant arm selection and the
   final noise estimate matches the closed-form combination.
6. Kernel type — THIN_CROSS vs THICK_CROSS on a uniform input; the wider arms of
   THICK_CROSS contribute ``(2*guard+1)`` times more cells, which is
   verified against the analytic CFAR formula.
7. Fixed threshold floor — output is clipped below by ``fixed_threshold``.
8. Sidelobe compensation — output is raised to at least ``max * 10^(dB/10)``
   (1D: global max, 2D: per-axis max independently per axis).
9. Boundary behavior — small arrays where the window is fully clipped on one
   side (asymmetric arm counts) and where it is fully empty (threshold = inf).
10. Monte Carlo FPR — on i.i.d. exponential noise the empirical FPR falls
    within method-specific bounds documenting CA / GO / SO selection bias.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool.a2.algo.nodes._cfar_nodes import CFAR1DThresholdNode, CFAR2DThresholdNode
from acconeer.exptool.a2.algo.nodes._cfar_subnodes import CFARAggregateMethod, CFARKernelType


# --- Constants ---

_RTOL = 1e-10
_ATOL = 1e-12
_FPR = 1e-2


# --- Helpers ---


def _cfar_scaling(n: int, fpr: float = _FPR) -> float:
    """Closed-form CFAR scaling factor for ``n`` reference cells at ``fpr``.

    The threshold at a cell is ``noise_est * cfar_scaling(N)``; this helper
    lets every test below reference the same canonical formula.
    """
    return n * (fpr ** (-1.0 / n) - 1.0)


# --- Plotting helpers ---
#
# Figures are only built and displayed when pytest is run with ``--plot-show``
# or, on failure, with ``--plot-show-on-fail`` (flags defined in
# ``tests/conftest.py``). Tests guard their plotting block on the
# ``plot_show_enabled`` fixture and lazy-import ``matplotlib.pyplot`` inside —
# the import never happens when the flags are absent.


def _make_1d_cfar_figure(
    plt: Any,
    title: str,
    data: npt.NDArray[np.float64],
    threshold: npt.NDArray[np.float64],
    *,
    cut_idx: int | None = None,
    guard_radius: int = 0,
    ref_radius: int = 0,
    expected_threshold: float | None = None,
    sidelobe_floor: float | None = None,
) -> Any:
    """1D CFAR figure: signal + threshold + reference/guard shading around the CUT.

    The shaded spans show which cells the CFAR window covers at the CUT
    (left ref arm, guard, right ref arm); they are skipped when ``cut_idx`` is
    None. ``expected_threshold`` overlays the closed-form value being asserted
    so a failure is visible as a gap between the curve and the line.
    """
    n = len(data)
    t = np.arange(n)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.set_title(title)
    ax.plot(t, data, label="input", color="steelblue", linewidth=1.5)
    ax.plot(t, threshold, label="CFAR threshold", color="crimson", linewidth=1.5)
    if cut_idx is not None:
        ax.axvline(cut_idx, color="black", linestyle=":", linewidth=1.0, label=f"CUT={cut_idx}")
        if ref_radius > 0:
            l_start = max(0, cut_idx - guard_radius - ref_radius)
            l_end = max(0, cut_idx - guard_radius)
            r_start = min(n, cut_idx + guard_radius + 1)
            r_end = min(n, cut_idx + guard_radius + ref_radius + 1)
            if l_end > l_start:
                ax.axvspan(
                    l_start - 0.5, l_end - 0.5, color="orange", alpha=0.18, label="left ref arm"
                )
            if r_end > r_start:
                ax.axvspan(
                    r_start - 0.5, r_end - 0.5, color="green", alpha=0.18, label="right ref arm"
                )
        if guard_radius > 0:
            g_lo = max(0, cut_idx - guard_radius)
            g_hi = min(n, cut_idx + guard_radius + 1)
            ax.axvspan(g_lo - 0.5, g_hi - 0.5, color="gray", alpha=0.25, label="guard")
    if expected_threshold is not None and np.isfinite(expected_threshold):
        ax.axhline(
            expected_threshold,
            color="purple",
            linestyle="--",
            linewidth=1.0,
            label=f"expected = {expected_threshold:.4g}",
        )
    if sidelobe_floor is not None and np.isfinite(sidelobe_floor):
        ax.axhline(
            sidelobe_floor,
            color="goldenrod",
            linestyle="-.",
            linewidth=1.0,
            label=f"sidelobe floor = {sidelobe_floor:.4g}",
        )
    ax.set_xlabel("cell index")
    ax.set_ylabel("value")
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    return fig


def _add_cfar_arm_rectangles(
    ax: Any,
    cut_row: int,
    cut_col: int,
    guard_radii: tuple[int, int],
    ref_radii: tuple[int, int],
    kernel_type: CFARKernelType,
    shape: tuple[int, int],
    color: str = "white",
) -> None:
    """Overlay the four CFAR reference arms as dashed rectangles on a heatmap.

    Arm geometry follows :class:`CFAR2DThresholdNode`: ``ref_radii[0]``
    and ``ref_radii[1]`` are the radii along axes 0 and 1; ``guard_radii``
    likewise. THICK_CROSS thickens each arm perpendicular by
    ``2 * guard_perp + 1`` cells.
    """
    from matplotlib.patches import Rectangle

    n_g0, n_g1 = guard_radii
    n_r0, n_r1 = ref_radii
    n0, n1 = shape

    def clamp(v: int, hi: int) -> int:
        return max(0, min(v, hi))

    # Ranges along axis 0 (rows) for left/right arms.
    l_start = clamp(cut_row - n_g0 - n_r0, n0)
    l_end = clamp(cut_row - n_g0, n0)
    r_start = clamp(cut_row + n_g0 + 1, n0)
    r_end = clamp(cut_row + n_g0 + n_r0 + 1, n0)
    # Ranges along axis 1 (cols) for near/far arms.
    n_start = clamp(cut_col - n_g1 - n_r1, n1)
    n_end = clamp(cut_col - n_g1, n1)
    f_start = clamp(cut_col + n_g1 + 1, n1)
    f_end = clamp(cut_col + n_g1 + n_r1 + 1, n1)
    # Perpendicular thickness: THIN_CROSS = 1 cell, THICK_CROSS = (2*guard_perp+1).
    if kernel_type == CFARKernelType.THICK_CROSS:
        row_thick_lo = clamp(cut_row - n_g0, n0)
        row_thick_hi = clamp(cut_row + n_g0 + 1, n0)
        col_thick_lo = clamp(cut_col - n_g1, n1)
        col_thick_hi = clamp(cut_col + n_g1 + 1, n1)
    else:
        row_thick_lo = clamp(cut_row, n0)
        row_thick_hi = clamp(cut_row + 1, n0)
        col_thick_lo = clamp(cut_col, n1)
        col_thick_hi = clamp(cut_col + 1, n1)

    rects = [
        # Left arm (axis 0 < CUT): rows [l_start, l_end), perpendicular width across axis 1.
        (l_start, l_end, col_thick_lo, col_thick_hi, "left"),
        # Right arm (axis 0 > CUT).
        (r_start, r_end, col_thick_lo, col_thick_hi, "right"),
        # Near arm (axis 1 < CUT): cols [n_start, n_end), perpendicular height across axis 0.
        (row_thick_lo, row_thick_hi, n_start, n_end, "near"),
        # Far arm (axis 1 > CUT).
        (row_thick_lo, row_thick_hi, f_start, f_end, "far"),
    ]
    for row_lo, row_hi, col_lo, col_hi, label in rects:
        if row_hi <= row_lo or col_hi <= col_lo:
            continue
        # Rectangle xy is (col, row) in imshow coordinates; -0.5 aligns with pixel edges.
        rect = Rectangle(
            (col_lo - 0.5, row_lo - 0.5),
            col_hi - col_lo,
            row_hi - row_lo,
            linewidth=1.2,
            edgecolor=color,
            facecolor="none",
            linestyle="--",
            label=label,
        )
        ax.add_patch(rect)


def _make_2d_cfar_figure(
    plt: Any,
    title: str,
    data: npt.NDArray[np.float64],
    threshold: npt.NDArray[np.float64],
    *,
    cut: tuple[int, int] | None = None,
    guard_radii: tuple[int, int] | None = None,
    ref_radii: tuple[int, int] | None = None,
    kernel_type: CFARKernelType = CFARKernelType.THIN_CROSS,
    expected_threshold: float | None = None,
) -> Any:
    """Three-panel CFAR figure (signal/threshold slices + heatmap with arms).

    Panels mirror the reference visualization script used during development:
    a slice across axis 0 through the CUT, a slice across axis 1 through the
    CUT, and the full 2D map with the CFAR arm rectangles overlaid. The CUT
    is centered on the cell with the largest input value when not specified.
    """
    if cut is None:
        cut = tuple(int(i) for i in np.unravel_index(np.argmax(data), data.shape))  # type: ignore[assignment]
    assert cut is not None
    cut_row, cut_col = cut

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    ax_row_slice, ax_col_slice, ax_heat = axes
    fig.suptitle(title)

    # Panel 1: slice along axis 0 at cut_col (varies left/right arms).
    axis0 = np.arange(data.shape[0])
    ax_row_slice.plot(axis0, data[:, cut_col], color="steelblue", label="input")
    ax_row_slice.plot(axis0, threshold[:, cut_col], color="crimson", label="CFAR threshold")
    ax_row_slice.axvline(cut_row, color="black", linestyle=":", linewidth=1.0, label="CUT")
    if expected_threshold is not None and np.isfinite(expected_threshold):
        ax_row_slice.axhline(
            expected_threshold,
            color="purple",
            linestyle="--",
            linewidth=1.0,
            label=f"expected = {expected_threshold:.4g}",
        )
    ax_row_slice.set_title(f"axis 0 slice @ col={cut_col}")
    ax_row_slice.set_xlabel("axis 0 index")
    ax_row_slice.legend(loc="best", fontsize=8)

    # Panel 2: slice along axis 1 at cut_row (varies near/far arms).
    axis1 = np.arange(data.shape[1])
    ax_col_slice.plot(axis1, data[cut_row, :], color="steelblue", label="input")
    ax_col_slice.plot(axis1, threshold[cut_row, :], color="crimson", label="CFAR threshold")
    ax_col_slice.axvline(cut_col, color="black", linestyle=":", linewidth=1.0, label="CUT")
    if expected_threshold is not None and np.isfinite(expected_threshold):
        ax_col_slice.axhline(
            expected_threshold,
            color="purple",
            linestyle="--",
            linewidth=1.0,
            label=f"expected = {expected_threshold:.4g}",
        )
    ax_col_slice.set_title(f"axis 1 slice @ row={cut_row}")
    ax_col_slice.set_xlabel("axis 1 index")
    ax_col_slice.legend(loc="best", fontsize=8)

    # Panel 3: heatmap with CFAR arms overlaid.
    im = ax_heat.imshow(data, aspect="auto", origin="upper", cmap="viridis")
    fig.colorbar(im, ax=ax_heat, label="value")
    ax_heat.scatter(cut_col, cut_row, color="white", edgecolors="black", zorder=10, label="CUT")
    if guard_radii is not None and ref_radii is not None:
        _add_cfar_arm_rectangles(
            ax_heat, cut_row, cut_col, guard_radii, ref_radii, kernel_type, data.shape
        )
    ax_heat.set_title(f"heatmap ({kernel_type.value})")
    ax_heat.set_xlabel("axis 1")
    ax_heat.set_ylabel("axis 0")
    ax_heat.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    return fig


# --- Group 1: Constructor validation ---
#
# The two guards in __init__ reject ``theoretical_fpr`` outside (0, 1) and any
# non-negative entry in ``side_lobe_compensation_dB``. These tests exercise
# each branch with a representative bad value and confirm a ValueError fires.
# The 2D node has a tuple-shaped sidelobe parameter, so both elements are
# tested independently to catch a guard that only checks the first.


@pytest.mark.parametrize("fpr", [0.0, 1.0, -0.1, 1.5])
def test_1d_node_rejects_fpr_out_of_unit_interval(fpr: float) -> None:
    """``theoretical_fpr`` must be strictly in (0, 1)."""
    with pytest.raises(ValueError, match="theoretical_fpr"):
        CFAR1DThresholdNode(input_shape=(20,), guard_radius=1, ref_radius=4, theoretical_fpr=fpr)


def test_1d_node_rejects_non_negative_sidelobe_dB() -> None:
    """``side_lobe_compensation_dB`` must be smaller than zero (it is a dB *below* max)."""
    with pytest.raises(ValueError, match="side_lobe_compensation_dB"):
        CFAR1DThresholdNode(
            input_shape=(20,), guard_radius=1, ref_radius=4, side_lobe_compensation_dB=0.0
        )


@pytest.mark.parametrize("bad_shape", [(4, 4), (2, 3, 4), ()])
def test_1d_node_rejects_non_1d_input_shape(bad_shape: tuple[int, ...]) -> None:
    """``CFAR1DThresholdNode`` only supports 1D inputs — guard against multi-dim shapes."""
    with pytest.raises(ValueError, match="1D input_shape"):
        CFAR1DThresholdNode(
            input_shape=bad_shape,  # type: ignore[arg-type]
            guard_radius=1,
            ref_radius=2,
        )


@pytest.mark.parametrize("fpr", [0.0, 1.0, -0.1, 1.5])
def test_2d_node_rejects_fpr_out_of_unit_interval(fpr: float) -> None:
    """``theoretical_fpr`` must be strictly in (0, 1) (2D)."""
    with pytest.raises(ValueError, match="theoretical_fpr"):
        CFAR2DThresholdNode(
            input_shape=(20, 20), guard_radii=(1, 1), ref_radii=(4, 4), theoretical_fpr=fpr
        )


@pytest.mark.parametrize(
    "sidelobe",
    [(0.0, -10.0), (-10.0, 0.0), (1.0, None), (None, 0.5)],
)
def test_2d_node_rejects_non_negative_sidelobe_dB(
    sidelobe: tuple[float | None, float | None],
) -> None:
    """Either element of ``side_lobe_compensation_dB`` must be smaller than zero or None."""
    with pytest.raises(ValueError, match="side_lobe_compensation_dB"):
        CFAR2DThresholdNode(
            input_shape=(20, 20),
            guard_radii=(1, 1),
            ref_radii=(4, 4),
            side_lobe_compensation_dB=sidelobe,
        )


# --- Group 2: Input validation ---
#
# execute() checks that the input array shape matches the ``input_shape`` the
# node was constructed with. Any mismatch — wrong ndim, wrong length, wrong
# axis sizes — should raise a ValueError naming the expected shape so the
# caller can see what was wrong.


def test_1d_execute_rejects_shape_mismatch() -> None:
    """``map_1d`` shape must equal ``input_shape`` (covers wrong ndim and wrong length)."""
    node = CFAR1DThresholdNode(input_shape=(16,), guard_radius=1, ref_radius=2)
    with pytest.raises(ValueError, match="expected input of shape"):
        node.execute(np.ones((4, 4), dtype=np.float64))
    with pytest.raises(ValueError, match="expected input of shape"):
        node.execute(np.ones(17, dtype=np.float64))


def test_2d_execute_rejects_shape_mismatch() -> None:
    """``map_2d`` shape must equal ``input_shape`` (covers wrong ndim and wrong axis sizes)."""
    node = CFAR2DThresholdNode(input_shape=(4, 4), guard_radii=(1, 1), ref_radii=(2, 2))
    with pytest.raises(ValueError, match="expected input of shape"):
        node.execute(np.ones(16, dtype=np.float64))
    with pytest.raises(ValueError, match="expected input of shape"):
        node.execute(np.ones((4, 5), dtype=np.float64))


# --- Group 3: Constant noise floor ---
#
# When the input is flat at value ``n``, every reference cell holds the same
# value, so any aggregate method collapses to ``noise_est = n`` at interior
# cells (where the window is unclipped). The threshold then equals
# ``n * cfar_scaling(N)`` where ``N`` is the number of cells contributed by
# the chosen aggregate. The test asserts that interior cells match this
# closed form exactly. This is the single most informative test in the
# suite: any bug in the integral image, the arm clipping, the aggregate, or
# the scaling formula breaks it.


def test_1d_constant_noise_matches_cfar_formula_at_interior_cells(
    plot_figures: list, plot_show_enabled: bool
) -> None:
    """Flat input ``n`` → threshold = ``n * N*(fpr^(-1/N) - 1)`` at interior cells."""
    n = 4.0
    guard, ref = 1, 5
    data = np.full(30, n, dtype=np.float64)
    node = CFAR1DThresholdNode(
        input_shape=data.shape, guard_radius=guard, ref_radius=ref, theoretical_fpr=_FPR
    )
    out = node.execute(data)

    # CA combines both arms (2 * ref cells total).
    expected = n * _cfar_scaling(2 * ref)
    # Interior cells: window unclipped on both sides → indices [guard+ref, N-1-guard-ref].
    interior = slice(guard + ref, len(data) - guard - ref)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_1d_cfar_figure(
                plt,
                f"1D constant noise (n={n}, guard={guard}, ref={ref})",
                data,
                out,
                cut_idx=len(data) // 2,
                guard_radius=guard,
                ref_radius=ref,
                expected_threshold=expected,
            )
        )

    np.testing.assert_allclose(out[interior], expected, atol=_ATOL, rtol=_RTOL)


def test_2d_constant_noise_matches_cfar_formula_at_interior_cells_cross() -> None:
    """Flat input ``n`` with THIN_CROSS kernel → threshold = ``n * cfar_scaling(2*ref0 + 2*ref1)``."""
    n = 4.0
    guard, ref = (1, 2), (3, 4)
    data = np.full((20, 20), n, dtype=np.float64)
    node = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=guard,
        ref_radii=ref,
        kernel_type=CFARKernelType.THIN_CROSS,
        aggregate_method=(CFARAggregateMethod.CA, CFARAggregateMethod.CA),
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)

    total_cells = 2 * ref[0] + 2 * ref[1]
    expected = n * _cfar_scaling(total_cells)
    interior_0 = slice(guard[0] + ref[0], data.shape[0] - guard[0] - ref[0])
    interior_1 = slice(guard[1] + ref[1], data.shape[1] - guard[1] - ref[1])
    np.testing.assert_allclose(out[interior_0, interior_1], expected, atol=_ATOL, rtol=_RTOL)


# --- Group 4: 1D aggregate methods ---
#
# Construct an asymmetric input where the left ref arm holds value ``low`` and
# the right ref arm holds value ``high``. The aggregate method picks:
#   * CA: pool both arms → noise = (low+high)/2, N = 2*ref
#   * SO: pick the lower-mean arm → noise = low,        N = ref
#   * GO: pick the higher-mean arm → noise = high,      N = ref
# A single test parameterizes over the three methods so the expected algebra
# stays visible side-by-side. The CUT itself is set to 0 so it cannot leak
# into either arm.


@pytest.mark.parametrize(
    ("method", "expected_noise_fn", "expected_n_fn"),
    [
        (CFARAggregateMethod.CA, lambda lo, hi, r: (lo + hi) / 2, lambda r: 2 * r),
        (CFARAggregateMethod.SO, lambda lo, hi, r: lo, lambda r: r),
        (CFARAggregateMethod.GO, lambda lo, hi, r: hi, lambda r: r),
    ],
    ids=["CA", "SO", "GO"],
)
def test_1d_aggregate_methods_select_expected_arm(
    method: CFARAggregateMethod,
    expected_noise_fn,  # type: ignore[no-untyped-def]
    expected_n_fn,  # type: ignore[no-untyped-def]
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """CA pools both arms; SO/GO pick the lower / higher mean arm."""
    low, high = 1.0, 10.0
    ref, guard = 5, 0
    # [low x ref | CUT=0 | high x ref], CUT at index ref.
    data = np.concatenate(
        [np.full(ref, low), np.array([0.0]), np.full(ref, high)],
    ).astype(np.float64)
    cut_idx = ref

    node = CFAR1DThresholdNode(
        input_shape=data.shape,
        guard_radius=guard,
        ref_radius=ref,
        aggregate_method=method,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)

    expected_noise = expected_noise_fn(low, high, ref)
    expected_n = expected_n_fn(ref)
    expected_threshold = expected_noise * _cfar_scaling(expected_n)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_1d_cfar_figure(
                plt,
                f"1D aggregate {method.value} (low={low}, high={high}, ref={ref})",
                data,
                out,
                cut_idx=cut_idx,
                guard_radius=guard,
                ref_radius=ref,
                expected_threshold=expected_threshold,
            )
        )

    np.testing.assert_allclose(out[cut_idx], expected_threshold, atol=_ATOL, rtol=_RTOL)


def test_1d_so_prefers_full_arm_over_partial_arm_with_lower_mean() -> None:
    """SO breaks ties by rank: a full arm wins over a partial arm with a lower mean.

    Without the rank-first tiebreak, SO would pick the partial right arm (mean=1).
    With it (the documented behavior), SO picks the full left arm (mean=10) and the
    threshold is ``10 * cfar_scaling(ref)`` rather than ``1 * cfar_scaling(1)``.
    """
    ref, guard = 3, 0
    # CUT at index 3: left arm spans [0, 3) — full (rank=2, mean=10);
    # right arm spans [4, 7) clipped to [4, 5) — partial (rank=1, mean=1).
    data = np.array([10.0, 10.0, 10.0, 0.0, 1.0], dtype=np.float64)
    node = CFAR1DThresholdNode(
        input_shape=data.shape,
        guard_radius=guard,
        ref_radius=ref,
        aggregate_method=CFARAggregateMethod.SO,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    expected = 10.0 * _cfar_scaling(ref)
    np.testing.assert_allclose(out[3], expected, atol=_ATOL, rtol=_RTOL)


# --- Group 5: 2D aggregate methods ---
#
# A handcrafted 2D map gives each of the four arms a distinct, controllable
# value at the center CUT. For each aggregate method the expected noise
# estimate is computed as the count-weighted combination of the arms the
# method selects, and the test checks the threshold at the CUT matches
# ``noise * cfar_scaling(N_total)``. This exercises all 11 enum branches.
#
# Arm naming follows the source: "left"/"right" vary along axis 0, "near"/"far"
# vary along axis 1 (independent of the docstring's visual layout). For a
# centered CUT with the THIN_CROSS kernel, each arm has exactly ``ref_radius``
# cells, so the count-weighted mean is just the arithmetic mean over the
# arms picked by the method.


def _make_2d_arms_map(
    cut_row: int,
    cut_col: int,
    guard: tuple[int, int],
    ref: tuple[int, int],
    left: float,
    right: float,
    near: float,
    far: float,
    background: float = 0.0,
) -> npt.NDArray[np.float64]:
    """Build a 2D map giving each THIN_CROSS-kernel arm a distinct uniform value.

    Cells outside the four arms (and the guard region) are filled with
    ``background``; the CUT itself is also ``background``. This isolates the
    contribution of each arm so the aggregate's algebra is exact.
    """
    n_guard_0, n_guard_1 = guard
    n_ref_0, n_ref_1 = ref
    n0 = cut_row + n_guard_0 + n_ref_0 + 1
    n1 = cut_col + n_guard_1 + n_ref_1 + 1
    data = np.full((n0, n1), background, dtype=np.float64)
    # left/right vary along axis 0 at axis-1 = cut_col
    data[cut_row - n_guard_0 - n_ref_0 : cut_row - n_guard_0, cut_col] = left
    data[cut_row + n_guard_0 + 1 : cut_row + n_guard_0 + n_ref_0 + 1, cut_col] = right
    # near/far vary along axis 1 at axis-0 = cut_row
    data[cut_row, cut_col - n_guard_1 - n_ref_1 : cut_col - n_guard_1] = near
    data[cut_row, cut_col + n_guard_1 + 1 : cut_col + n_guard_1 + n_ref_1 + 1] = far
    return data


_REF_2D = (4, 3)  # ref_radii (axis0, axis1)
_GUARD_2D = (1, 1)
_CUT = (10, 10)
_L, _R, _NV, _F = 1.0, 5.0, 7.0, 3.0  # arm values: left, right, near, far


def _avg(*arms: float) -> tuple[float, int]:
    """Return (noise_est, total_count) for averaging arms each of length ref."""
    ref0, ref1 = _REF_2D
    counts = []
    total = 0.0
    for name, value in zip(("left", "right", "near", "far"), arms):
        if value is None:  # pragma: no cover - not used
            continue
        c = ref0 if name in ("left", "right") else ref1
        counts.append(c)
        total += value * c
    n = sum(counts)
    return total / n, n


def _pick(name: str, value: float) -> tuple[float, int]:
    """Single-arm noise estimate (used by SO/GO selection)."""
    ref0, ref1 = _REF_2D
    c = ref0 if name in ("left", "right") else ref1
    return value, c


_2DMethod = tuple[CFARAggregateMethod, CFARAggregateMethod]


_AGG_2D_CASES: list[tuple[_2DMethod, tuple[float, int]]] = [
    # All four arms averaged together.
    ((CFARAggregateMethod.CA, CFARAggregateMethod.CA), _avg(_L, _R, _NV, _F)),
    # SO on each axis → pick min-mean arm from each pair, then pool.
    (
        (CFARAggregateMethod.SO, CFARAggregateMethod.SO),
        # axis 0 min(left, right) = left (1.0); axis 1 min(near, far) = far (3.0)
        (
            (_L * _REF_2D[0] + _F * _REF_2D[1]) / (_REF_2D[0] + _REF_2D[1]),
            _REF_2D[0] + _REF_2D[1],
        ),
    ),
    # GO on each axis → pick max-mean arm from each pair, then pool.
    (
        (CFARAggregateMethod.GO, CFARAggregateMethod.GO),
        # axis 0 max = right (5.0); axis 1 max = near (7.0)
        (
            (_R * _REF_2D[0] + _NV * _REF_2D[1]) / (_REF_2D[0] + _REF_2D[1]),
            _REF_2D[0] + _REF_2D[1],
        ),
    ),
    # CA on axis 0 only (axis 1 dropped).
    (
        (CFARAggregateMethod.CA, CFARAggregateMethod.DROP),
        ((_L + _R) / 2, 2 * _REF_2D[0]),
    ),
    # CA on axis 1 only (axis 0 dropped).
    (
        (CFARAggregateMethod.DROP, CFARAggregateMethod.CA),
        ((_NV + _F) / 2, 2 * _REF_2D[1]),
    ),
    # CA axis 0 + GO axis 1 → left+right pooled, plus max(near,far)=near.
    (
        (CFARAggregateMethod.CA, CFARAggregateMethod.GO),
        (
            ((_L + _R) * _REF_2D[0] + _NV * _REF_2D[1]) / (2 * _REF_2D[0] + _REF_2D[1]),
            2 * _REF_2D[0] + _REF_2D[1],
        ),
    ),
    # CA axis 0 + SO axis 1 → left+right pooled, plus min(near,far)=far.
    (
        (CFARAggregateMethod.CA, CFARAggregateMethod.SO),
        (
            ((_L + _R) * _REF_2D[0] + _F * _REF_2D[1]) / (2 * _REF_2D[0] + _REF_2D[1]),
            2 * _REF_2D[0] + _REF_2D[1],
        ),
    ),
    # SO axis 0 (=left) + GO axis 1 (=near).
    (
        (CFARAggregateMethod.SO, CFARAggregateMethod.GO),
        (
            (_L * _REF_2D[0] + _NV * _REF_2D[1]) / (_REF_2D[0] + _REF_2D[1]),
            _REF_2D[0] + _REF_2D[1],
        ),
    ),
    # GO axis 0 (=right) + CA axis 1 (near+far pooled).
    (
        (CFARAggregateMethod.GO, CFARAggregateMethod.CA),
        (
            ((_NV + _F) * _REF_2D[1] + _R * _REF_2D[0]) / (2 * _REF_2D[1] + _REF_2D[0]),
            2 * _REF_2D[1] + _REF_2D[0],
        ),
    ),
    # SO axis 0 (=left) + CA axis 1 (near+far pooled).
    (
        (CFARAggregateMethod.SO, CFARAggregateMethod.CA),
        (
            ((_NV + _F) * _REF_2D[1] + _L * _REF_2D[0]) / (2 * _REF_2D[1] + _REF_2D[0]),
            2 * _REF_2D[1] + _REF_2D[0],
        ),
    ),
    # GO axis 0 (=right) + SO axis 1 (=far).
    (
        (CFARAggregateMethod.GO, CFARAggregateMethod.SO),
        (
            (_F * _REF_2D[1] + _R * _REF_2D[0]) / (_REF_2D[0] + _REF_2D[1]),
            _REF_2D[0] + _REF_2D[1],
        ),
    ),
]


def _2d_method_id(m: _2DMethod) -> str:
    return f"{m[0].value}_{m[1].value}"


@pytest.mark.parametrize(
    ("method", "expected"),
    _AGG_2D_CASES,
    ids=[_2d_method_id(m) for m, _ in _AGG_2D_CASES],
)
def test_2d_aggregate_methods_produce_expected_threshold(
    method: _2DMethod,
    expected: tuple[float, int],
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """All 11 aggregate methods produce the closed-form threshold at the CUT.

    Each arm carries a distinct uniform value, so any method's noise estimate
    is a count-weighted average over the arms it selects. The expected pair
    ``(noise, N)`` is precomputed per method in ``_AGG_2D_CASES``.
    """
    data = _make_2d_arms_map(*_CUT, _GUARD_2D, _REF_2D, _L, _R, _NV, _F)
    node = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=_GUARD_2D,
        ref_radii=_REF_2D,
        kernel_type=CFARKernelType.THIN_CROSS,
        aggregate_method=method,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    expected_noise, expected_n = expected
    expected_threshold = expected_noise * _cfar_scaling(expected_n)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_2d_cfar_figure(
                plt,
                f"2D aggregate {_2d_method_id(method)} — expected noise={expected_noise:.3f} N={expected_n}",
                data,
                out,
                cut=_CUT,
                guard_radii=_GUARD_2D,
                ref_radii=_REF_2D,
                kernel_type=CFARKernelType.THIN_CROSS,
                expected_threshold=expected_threshold,
            )
        )

    np.testing.assert_allclose(out[_CUT], expected_threshold, atol=_ATOL, rtol=_RTOL)


# --- Group 6: Kernel type ---
#
# THICK_CROSS widens each arm by ``2*guard_perp + 1`` cells in the
# perpendicular direction (compared to the 1-cell wide THIN_CROSS arms). On a flat
# input both kernels yield ``noise_est = n``, but the cell counts differ, so
# the CFAR scaling factors differ. The test compares thresholds at an
# interior cell to the analytic formula for each kernel.


def test_2d_extended_cross_kernel_widens_arms_by_perpendicular_window(
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """THICK_CROSS arms widen to ``(2*guard+1)`` perpendicular cells."""
    n = 2.0
    guard = (2, 3)
    ref = (4, 5)
    data = np.full((30, 30), n, dtype=np.float64)
    w0 = 2 * guard[0] + 1
    w1 = 2 * guard[1] + 1
    total_cross = 2 * ref[0] + 2 * ref[1]
    total_ext = 2 * ref[0] * w1 + 2 * ref[1] * w0

    node_cross = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=guard,
        ref_radii=ref,
        kernel_type=CFARKernelType.THIN_CROSS,
        theoretical_fpr=_FPR,
    )
    node_ext = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=guard,
        ref_radii=ref,
        kernel_type=CFARKernelType.THICK_CROSS,
        theoretical_fpr=_FPR,
    )
    out_cross = node_cross.execute(data)
    out_ext = node_ext.execute(data)

    interior = (15, 15)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_2d_cfar_figure(
                plt,
                f"THIN_CROSS kernel (N={total_cross}, threshold={out_cross[interior]:.4g})",
                data,
                out_cross,
                cut=interior,
                guard_radii=guard,
                ref_radii=ref,
                kernel_type=CFARKernelType.THIN_CROSS,
                expected_threshold=n * _cfar_scaling(total_cross),
            )
        )
        plot_figures.append(
            _make_2d_cfar_figure(
                plt,
                f"THICK_CROSS kernel (N={total_ext}, threshold={out_ext[interior]:.4g})",
                data,
                out_ext,
                cut=interior,
                guard_radii=guard,
                ref_radii=ref,
                kernel_type=CFARKernelType.THICK_CROSS,
                expected_threshold=n * _cfar_scaling(total_ext),
            )
        )

    np.testing.assert_allclose(
        out_cross[interior], n * _cfar_scaling(total_cross), atol=_ATOL, rtol=_RTOL
    )
    np.testing.assert_allclose(
        out_ext[interior], n * _cfar_scaling(total_ext), atol=_ATOL, rtol=_RTOL
    )
    # Larger N gives a *smaller* scaling factor → extended kernel threshold is lower.
    assert out_ext[interior] < out_cross[interior]


# --- Group 7: Fixed threshold floor ---
#
# ``fixed_threshold`` clips the output from below after CFAR scaling. The test
# uses a quiet input (so the CFAR-scaled threshold is well below the floor)
# and asserts every cell sits at exactly the floor. Also covers the all-clipped
# regime, which is what makes ``fixed_threshold`` useful in practice.


def test_1d_fixed_threshold_floors_output() -> None:
    """Output is clipped from below by ``fixed_threshold``."""
    data = np.full(20, 0.1, dtype=np.float64)
    floor = 100.0
    node = CFAR1DThresholdNode(
        input_shape=data.shape,
        guard_radius=1,
        ref_radius=4,
        fixed_threshold=floor,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    np.testing.assert_allclose(out, floor, atol=_ATOL, rtol=_RTOL)


def test_2d_fixed_threshold_floors_output() -> None:
    """Output is clipped from below by ``fixed_threshold`` (2D)."""
    data = np.full((12, 12), 0.1, dtype=np.float64)
    floor = 50.0
    node = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=(1, 1),
        ref_radii=(2, 2),
        fixed_threshold=floor,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    np.testing.assert_allclose(out, floor, atol=_ATOL, rtol=_RTOL)


# --- Group 8: Sidelobe compensation ---
#
# After CFAR scaling and the fixed-threshold floor, the threshold is also
# raised to at least ``max * 10^(dB/10)``. For 1D the max is global; for 2D
# the compensation is applied per axis (axis 0 → per-column max, axis 1 →
# per-row max), and each element of the tuple is independently optional.
# Tests cover (a) the floor is applied, (b) per-axis behavior is independent,
# and (c) the unused element being None has no effect.


def test_1d_sidelobe_compensation_floors_to_db_below_global_max(
    plot_figures: list, plot_show_enabled: bool
) -> None:
    """Threshold ≥ ``max(map) * 10^(dB/10)`` everywhere."""
    data = np.full(20, 0.01, dtype=np.float64)
    data[5] = 100.0  # global maximum
    db = -20.0  # floor at 100 * 10^-2 = 1.0
    node = CFAR1DThresholdNode(
        input_shape=data.shape,
        guard_radius=1,
        ref_radius=4,
        side_lobe_compensation_dB=db,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    expected_floor = data.max() * 10 ** (db / 10)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        fig = _make_1d_cfar_figure(
            plt,
            f"1D sidelobe compensation ({db} dB) — floor binds away from peak",
            data,
            out,
            cut_idx=15,
            guard_radius=1,
            ref_radius=4,
            expected_threshold=expected_floor,
            sidelobe_floor=expected_floor,
        )
        fig.axes[0].set_yscale("log")
        plot_figures.append(fig)

    assert np.all(out >= expected_floor - _ATOL)
    # At index 15 the CFAR window (left [10, 14), right [17, 20)) is past the
    # bright cell at index 5, so the noise estimate is ~0.01 and CFAR threshold
    # is tiny — the sidelobe floor binds → output ≈ floor.
    np.testing.assert_allclose(out[15], expected_floor, atol=_ATOL, rtol=_RTOL)


def test_2d_sidelobe_compensation_applies_per_axis_independently(
    plot_figures: list, plot_show_enabled: bool
) -> None:
    """Per-axis sidelobe floor uses ``max(map, axis=k)`` for axis k."""
    data = np.full((20, 20), 0.01, dtype=np.float64)
    data[5, 7] = 100.0  # one bright cell — axis-0 col 7 max = 100, axis-1 row 5 max = 100
    db_0, db_1 = -20.0, -30.0
    node = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=(1, 1),
        ref_radii=(2, 2),
        side_lobe_compensation_dB=(db_0, db_1),
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)

    expected_axis_0 = data.max(axis=0)[None, :] * 10 ** (db_0 / 10)
    expected_axis_1 = data.max(axis=1)[:, None] * 10 ** (db_1 / 10)
    expected_floor = np.maximum(expected_axis_0, expected_axis_1)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        fig = _make_2d_cfar_figure(
            plt,
            f"2D sidelobe compensation (axis0={db_0} dB, axis1={db_1} dB) — peak at (5, 7)",
            data,
            out,
            cut=(15, 7),
            guard_radii=(1, 1),
            ref_radii=(2, 2),
            kernel_type=CFARKernelType.THIN_CROSS,
            expected_threshold=float(expected_floor[15, 7]),
        )
        fig.axes[0].set_yscale("log")
        fig.axes[1].set_yscale("log")
        plot_figures.append(fig)

    assert np.all(out >= expected_floor - _ATOL)
    # At (15, 7) the CFAR window doesn't reach the bright cell at (5, 7), so
    # the noise estimate is ~0.01 and CFAR threshold is tiny. Column 7's axis-0
    # max is 100 → axis-0 floor = 1.0 binds → output ≈ floor.
    np.testing.assert_allclose(out[15, 7], expected_floor[15, 7], atol=_ATOL, rtol=_RTOL)


def test_2d_sidelobe_compensation_with_one_axis_none() -> None:
    """Setting only one axis applies only that axis's floor."""
    data = np.full((20, 20), 0.01, dtype=np.float64)
    data[5, 7] = 100.0
    db_0 = -20.0
    node_only_0 = CFAR2DThresholdNode(
        input_shape=data.shape,
        guard_radii=(1, 1),
        ref_radii=(2, 2),
        side_lobe_compensation_dB=(db_0, None),
        theoretical_fpr=_FPR,
    )
    out = node_only_0.execute(data)
    expected_axis_0 = data.max(axis=0)[None, :] * 10 ** (db_0 / 10)
    # Column 7 has the bright cell → floor binds; column 0 has none → floor ~ 0.01 * 0.01.
    np.testing.assert_allclose(out[15, 7], expected_axis_0[0, 7], atol=_ATOL, rtol=_RTOL)
    assert out[15, 0] < expected_axis_0[0, 7]


# --- Group 9: Boundary behavior ---
#
# Near the edges the reference window is clipped. The CFAR scaling formula
# evaluates with the *actual* cell count N, so the threshold stays finite
# (just based on fewer cells). When the window is fully empty on both sides
# — e.g. an N=1 array with a non-trivial guard — the threshold is infinite.
# These tests pin down both regimes.


def test_1d_boundary_uses_partial_window_when_one_side_is_clipped(
    plot_figures: list, plot_show_enabled: bool
) -> None:
    """Asymmetric boundary cell: only the right arm contributes."""
    n = 4.0
    ref, guard = 3, 0
    data = np.full(20, n, dtype=np.float64)
    node = CFAR1DThresholdNode(
        input_shape=data.shape,
        guard_radius=guard,
        ref_radius=ref,
        aggregate_method=CFARAggregateMethod.CA,
        theoretical_fpr=_FPR,
    )
    out = node.execute(data)
    # At index 0 the left arm is fully clipped (0 cells), right arm has ``ref`` cells.
    expected = n * _cfar_scaling(ref)

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_1d_cfar_figure(
                plt,
                f"1D boundary (CUT at edge → only right arm contributes, expected = n * cfar({ref}))",
                data,
                out,
                cut_idx=0,
                guard_radius=guard,
                ref_radius=ref,
                expected_threshold=expected,
            )
        )

    np.testing.assert_allclose(out[0], expected, atol=_ATOL, rtol=_RTOL)
    assert np.isfinite(out[0])


def test_1d_returns_inf_threshold_when_window_is_fully_empty() -> None:
    """Tiny array with guard so both arms clip away → threshold = inf."""
    data = np.ones(1, dtype=np.float64)
    node = CFAR1DThresholdNode(
        input_shape=data.shape, guard_radius=1, ref_radius=3, theoretical_fpr=_FPR
    )
    out = node.execute(data)
    assert np.isinf(out[0])


def test_2d_returns_inf_threshold_when_window_is_fully_empty() -> None:
    """1×1 input with non-trivial guard → no arm has any cell → threshold = inf."""
    data = np.ones((1, 1), dtype=np.float64)
    node = CFAR2DThresholdNode(
        input_shape=data.shape, guard_radii=(1, 1), ref_radii=(2, 2), theoretical_fpr=_FPR
    )
    out = node.execute(data)
    assert np.isinf(out[0, 0])


def test_1d_returns_inf_everywhere_when_guard_exceeds_array() -> None:
    """All-inf threshold: with ``guard_radius`` larger than the array can fit, every
    cell's reference window lies entirely past the array boundary on both sides,
    so no cell ever has any reference data. The CFAR scaling formula then evaluates
    with ``N == 0`` and the threshold is ``inf`` at every position."""
    data = np.ones(3, dtype=np.float64)
    node = CFAR1DThresholdNode(
        input_shape=data.shape, guard_radius=3, ref_radius=2, theoretical_fpr=_FPR
    )
    out = node.execute(data)
    assert np.all(np.isinf(out))


# --- Group 10: Monte Carlo FPR ---
#
# The node is cell-averaging CFAR throughout — each arm produces an unbiased
# mean of its reference cells. ``aggregate_method`` only decides *which*
# per-arm mean becomes the noise estimate: CA pools both arm sums into a
# single 2·ref-cell average; SO picks the smaller of the two per-arm means;
# GO picks the larger.
#
# The scaling formula ``T(N) = N * (fpr^(-1/N) - 1)`` delivers the target FPR
# only when the noise estimate is an unbiased mean of N i.i.d. exponential
# cells. The code does pass the correct ``N`` for each aggregate (``N=2·ref``
# for CA; ``N=ref`` for SO/GO), so the *count* is properly accounted for.
# What the formula does *not* compensate for is the **selection bias** of SO
# and GO: ``min(mean_L, mean_R)`` has expectation below the true noise
# floor, so the threshold ends up systematically too low and empirical FPR
# exceeds target; GO is the mirror case (threshold too high, FPR below
# target). These biases are inherent to the simple ``T(N)`` scaling and would
# require an order-statistic-aware formula to remove. The tests below pin
# each method's empirical FPR into a range that documents the bias and
# would flag a regression.
#
# The target FPR is set high (0.1) so each trial produces many exceedances,
# letting the estimate converge with only a few hundred trials (sub-second
# runtime). Adjacent CUTs in a trial share reference cells, so per-cell
# decisions are correlated; the *mean* is still unbiased.


def _empirical_fpr_1d(
    node: CFAR1DThresholdNode,
    N: int,
    n_trials: int,
    interior: slice,
    seed: int,
    record_trace: bool = False,
) -> tuple[float, list[float], npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Run ``n_trials`` independent exponential-noise trials; return empirical FPR.

    Counts CUT exceedances over interior cells (where the reference window is
    unclipped) and divides by the total cell count. With ``record_trace=True``
    also returns the running per-trial empirical FPR and a sample trial's
    data/threshold pair so the test can build a diagnostic figure.
    """
    rng = np.random.default_rng(seed)
    exceed = 0
    total = 0
    running: list[float] = []
    sample_data = np.empty(N, dtype=np.float64)
    sample_threshold = np.empty(N, dtype=np.float64)
    for trial in range(n_trials):
        data = rng.exponential(scale=1.0, size=N)
        threshold = node.execute(data)
        exceed += int(np.sum(data[interior] > threshold[interior]))
        total += data[interior].size
        if record_trace:
            running.append(exceed / total)
            if trial == 0:
                sample_data = data
                sample_threshold = threshold
    return exceed / total, running, sample_data, sample_threshold


# Per-method expected FPR ranges on i.i.d. exponential noise at target=0.1
# with guard=1, ref=8. Bounds are loose enough to survive seed variation
# (~0.005 1σ at these settings) but tight enough to catch regressions.
_FPR_RANGES_NO_SNR: list[tuple[CFARAggregateMethod, float, float]] = [
    (CFARAggregateMethod.CA, 0.085, 0.115),
    # SO's selection bias drives noise_est below the true floor → over-fires.
    (CFARAggregateMethod.SO, 0.12, 0.18),
    # GO's selection bias drives noise_est above the true floor → under-fires.
    (CFARAggregateMethod.GO, 0.04, 0.075),
]


@pytest.mark.parametrize(("method", "lo", "hi"), _FPR_RANGES_NO_SNR)
def test_1d_monte_carlo_fpr_per_aggregate_method(
    method: CFARAggregateMethod,
    lo: float,
    hi: float,
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """Empirical FPR on i.i.d. exponential noise falls within method-specific bounds.

    CA matches target; SO over-fires and GO under-fires due to the
    selection bias inherent to picking the smaller/larger of two arm means
    (the count is accounted for in the scaling formula, but the order-
    statistic bias is not).
    """
    target_fpr = 0.1
    N, n_trials = 500, 200
    guard, ref = 1, 8
    interior = slice(guard + ref, N - guard - ref)
    node = CFAR1DThresholdNode(
        input_shape=(N,),
        guard_radius=guard,
        ref_radius=ref,
        theoretical_fpr=target_fpr,
        aggregate_method=method,
    )
    empirical, running, sample_data, sample_threshold = _empirical_fpr_1d(
        node, N, n_trials, interior, seed=42, record_trace=True
    )

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        fig, (ax_trial, ax_fpr) = plt.subplots(1, 2, figsize=(14, 4))
        fig.suptitle(
            f"Monte Carlo FPR — {method.value} (empirical={empirical:.4f}, "
            f"target={target_fpr}, range=[{lo}, {hi}])"
        )
        t = np.arange(N)
        ax_trial.plot(t, sample_data, color="steelblue", linewidth=0.7, label="exponential noise")
        ax_trial.plot(t, sample_threshold, color="crimson", linewidth=1.0, label="CFAR threshold")
        exceed_mask = sample_data > sample_threshold
        exceed_mask[: interior.start] = False
        exceed_mask[interior.stop :] = False
        ax_trial.scatter(
            t[exceed_mask],
            sample_data[exceed_mask],
            color="black",
            s=18,
            zorder=5,
            label=f"exceedances ({int(exceed_mask.sum())})",
        )
        ax_trial.axvspan(interior.start, interior.stop, color="gray", alpha=0.08, label="interior")
        ax_trial.set_title("trial 0")
        ax_trial.set_xlabel("cell index")
        ax_trial.legend(loc="best", fontsize=8)

        ax_fpr.plot(
            np.arange(1, len(running) + 1), running, color="steelblue", label="running FPR"
        )
        ax_fpr.axhline(target_fpr, color="purple", linestyle="--", linewidth=1.0, label="target")
        ax_fpr.axhspan(lo, hi, color="green", alpha=0.12, label=f"expected band [{lo}, {hi}]")
        ax_fpr.set_title("empirical FPR vs trials")
        ax_fpr.set_xlabel("trial")
        ax_fpr.set_ylabel("cumulative empirical FPR")
        ax_fpr.legend(loc="best", fontsize=8)
        fig.tight_layout()
        plot_figures.append(fig)

    assert lo <= empirical <= hi, (
        f"{method.value}: empirical FPR {empirical:.4f} outside expected range "
        f"[{lo}, {hi}] for target {target_fpr}"
    )


# test_1d_monte_carlo_snr_selectability_keeps_fpr_near_target was removed
# during the sub-node refactor; its replacement will live alongside the new
# SNR-aware wrapper in :mod:`._d_az_el_heatmap_processing`.


def _empirical_fpr_2d(
    node: CFAR2DThresholdNode,
    shape: tuple[int, int],
    n_trials: int,
    interior_0: slice,
    interior_1: slice,
    seed: int,
) -> float:
    """2D analogue of ``_empirical_fpr_1d``.

    Counts CUT exceedances over the interior region (where the reference
    window is unclipped on both axes) and divides by the total cell count.
    Adjacent CUTs share reference cells; per-cell decisions are correlated
    but the mean stays unbiased.
    """
    rng = np.random.default_rng(seed)
    exceed = 0
    total = 0
    for _ in range(n_trials):
        data = rng.exponential(scale=1.0, size=shape)
        threshold = node.execute(data)
        interior_data = data[interior_0, interior_1]
        interior_thr = threshold[interior_0, interior_1]
        exceed += int(np.sum(interior_data > interior_thr))
        total += interior_data.size
    return exceed / total


# Per-method 2D FPR ranges with CA on both axes; the CFAR scaling formula
# is fed the pooled (sum, count) so the math is identical to the 1D CA case.
# SO/GO biases are documented in the 1D test group; the 2D test pins CA only
# because GO/SO biases compound non-trivially across axes and a precise
# theoretical range would distract from the regression intent.
_FPR_RANGES_2D_CA: list[tuple[tuple[CFARAggregateMethod, CFARAggregateMethod], float, float]] = [
    ((CFARAggregateMethod.CA, CFARAggregateMethod.CA), 0.085, 0.115),
]


@pytest.mark.parametrize(("aggregate_method", "lo", "hi"), _FPR_RANGES_2D_CA)
def test_2d_monte_carlo_fpr_ca_matches_target(
    aggregate_method: tuple[CFARAggregateMethod, CFARAggregateMethod],
    lo: float,
    hi: float,
) -> None:
    """Pinning the 2D CA-CFAR empirical FPR at the target — counterpart of the 1D Monte-Carlo
    group above. Mirrors that setup with a smaller map and trial count to keep runtime sub-second.
    """
    target_fpr = 0.1
    shape = (40, 40)
    n_trials = 80
    guard, ref = (1, 1), (4, 4)
    interior_0 = slice(guard[0] + ref[0], shape[0] - guard[0] - ref[0])
    interior_1 = slice(guard[1] + ref[1], shape[1] - guard[1] - ref[1])
    node = CFAR2DThresholdNode(
        input_shape=shape,
        guard_radii=guard,
        ref_radii=ref,
        theoretical_fpr=target_fpr,
        aggregate_method=aggregate_method,
    )
    empirical = _empirical_fpr_2d(node, shape, n_trials, interior_0, interior_1, seed=42)
    assert lo <= empirical <= hi, (
        f"2D {aggregate_method}: empirical FPR {empirical:.4f} outside "
        f"expected range [{lo}, {hi}] for target {target_fpr}"
    )
