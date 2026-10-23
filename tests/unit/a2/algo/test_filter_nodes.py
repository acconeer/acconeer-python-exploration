# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for ExponentialLowPassNode, DelayedExponentialHighPassNode,
and ExponentialHighPassNode.

Each node is described by a NodeSpec (class + transfer-function coefficients), and the
three test families below are parametrized once over _NODE_SPECS instead of duplicated
per class.

Test groups:

1. test_step_response
   Nodes are constructed with warmup=False so they use lp_constant directly from
   the first call, matching a fixed-coefficient IIR with zero initial state. Output
   is compared against scipy.signal.dlsim using the known transfer function H(z):

       ExponentialLowPassNode:          H(z) = (1 - α)·z / (z - α)
       DelayedExponentialHighPassNode:  H(z) = (z - 1) / (z - α)
       ExponentialHighPassNode:         H(z) = α·(z - 1) / (z - α)

   where α = lp_constant. The test signal has _N_PRE_STEP zero samples before the
   step so the step is visible in the plot. Covers float64 and complex128 — for
   complex the step is (1 + 1j); since filter coefficients are real, real and
   imaginary parts each equal the real step response.

2. test_warmup_convergence
   Nodes use warmup=True (default). The adaptive warmup ramps the effective alpha
   from 0 to lp_constant via warmup_filter_const(beta, n) = min(beta, n/(n+1)),
   reaching steady state faster than a cold-started fixed-coefficient IIR.
   Output is compared against dlsim started cold: the node must have smaller total
   squared deviation from steady state, confirming faster convergence.

   lp_constant=0 is excluded: warmup_filter_const(0, n)=0 always, so the node
   and reference are identical (both track input instantly).

3. test_sinusoid_response
   Each spatial element receives a sinusoid scaled by a distinct amplitude, verifying
   that the filter is applied independently per element (linearity, no spatial
   cross-contamination). Compared against the unit-sinusoid dlsim response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import numpy.typing as npt
import pytest
from scipy.signal import dlsim, dlti

from acconeer.exptool.a2.algo.nodes._filter_nodes import (
    DelayedExponentialHighPassNode,
    ExponentialHighPassNode,
    ExponentialLowPassNode,
)


# --- Node specs ---


@dataclass(frozen=True)
class NodeSpec:
    """Class + transfer-function pair driving the parametrized tests."""

    cls: type
    label: str
    tf_num: Callable[[float], list[float]]  # alpha -> numerator coefficients
    tf_den: Callable[[float], list[float]]  # alpha -> denominator coefficients


_NODE_SPECS = [
    NodeSpec(
        cls=ExponentialLowPassNode,
        label="ExponentialLowPassNode",
        tf_num=lambda a: [(1 - a), 0],
        tf_den=lambda a: [1, -a],
    ),
    NodeSpec(
        cls=DelayedExponentialHighPassNode,
        label="DelayedExponentialHighPassNode",
        tf_num=lambda a: [1, -1],
        tf_den=lambda a: [1, -a],
    ),
    NodeSpec(
        cls=ExponentialHighPassNode,
        label="ExponentialHighPassNode",
        tf_num=lambda a: [a, -a],
        tf_den=lambda a: [1, -a],
    ),
]


# Warmup steady-state per node: LP converges to 1.0 for a unit step,
# both HP variants converge to 0.0.
_WARMUP_STEADY_STATE: dict[type, float] = {
    ExponentialLowPassNode: 1.0,
    DelayedExponentialHighPassNode: 0.0,
    ExponentialHighPassNode: 0.0,
}


# --- Constants ---

# TF test signal: _N_PRE_STEP zeros then a unit step.
# The pre-step baseline makes the transient clearly visible in plots.
_N_PRE_STEP = 50
_N_POST_STEP = 300
_N_TEST = _N_PRE_STEP + _N_POST_STEP

# Warmup test: pure unit step, no pre-warmup.
# 300 samples is enough to see convergence even for alpha=0.99
# (time constant ≈ 1/(1-alpha) = 100 samples).
_N_WARMUP_TEST = 300

# TF tests: both dtypes, a few well-spaced α values, two shapes (1D scalar + 2D matrix).
_LP_CONSTANTS = [0.0, 0.5, 0.99]
_DTYPES: list[type] = [np.float64, np.complex128]
_INPUT_SHAPES = [(1,), (3, 4)]

# Warmup tests: float64 only — the ramp is dtype-agnostic; TF tests cover complex×warmup.
_WARMUP_LP_CONSTANTS = [0.5, 0.9, 0.95, 0.99]  # exclude 0: no warmup effect at alpha=0

# Sinusoid tests: float64 only (TF tests cover complex); two α values and two frequencies.
# Low freq is in LP passband / HP stopband; near-Nyquist is the reverse.
_SINUSOID_LP_CONSTANTS = [0.0, 0.9]
_SINUSOID_FREQS = [0.05, 0.4]  # low / near-Nyquist (normalized, cycles per sample)
# Each spatial element receives a sinusoid scaled by a distinct amplitude to verify
# that the filter acts independently per element with no spatial cross-contamination.
_SINUSOID_AMPLITUDES = np.array([1.0, 2.0, 3.0])
# Number of samples shown in sinusoid figures. Full _N_TEST is used for assertions;
# this just limits the plot so a few cycles are visible.
_N_SINUSOID_PLOT = 100

_SINUSOID_SHAPE = (len(_SINUSOID_AMPLITUDES),)


# --- Helpers ---


def _test_signal(dtype: type) -> npt.NDArray:
    """_N_PRE_STEP zeros followed by a unit step of _N_POST_STEP samples."""
    real = np.concatenate([np.zeros(_N_PRE_STEP), np.ones(_N_POST_STEP)])
    if np.issubdtype(dtype, np.complexfloating):
        return (real * (1 + 1j)).astype(np.complex128)
    return real.astype(np.float64)


def _pure_step(n: int, dtype: type) -> npt.NDArray:
    """Unit step of length n starting at t=0."""
    real = np.ones(n)
    if np.issubdtype(dtype, np.complexfloating):
        return (real * (1 + 1j)).astype(np.complex128)
    return real.astype(np.float64)


def _reference_response(sys: dlti, signal: npt.NDArray) -> npt.NDArray:
    """Simulate the discrete system against a real-valued signal via dlsim."""
    real_signal = signal.real if np.issubdtype(signal.dtype, np.complexfloating) else signal
    _, y = dlsim(sys, real_signal)
    return y.ravel()


def _sinusoid_array(n: int, freq: float) -> npt.NDArray:
    """Sinusoid of length n at normalized frequency freq, shaped (n, len(_SINUSOID_AMPLITUDES)).
    Each column is a unit sinusoid scaled by the corresponding _SINUSOID_AMPLITUDES entry."""
    base = np.sin(2 * np.pi * freq * np.arange(n))
    return np.outer(base, _SINUSOID_AMPLITUDES).astype(np.float64)


def _make_sinusoid_figure(
    plt: Any,
    title: str,
    actual: npt.NDArray,
    unit_reference: npt.NDArray,
    dtype: type,
    unit_input: npt.NDArray,
) -> Any:
    """One figure showing all amplitudes over _N_SINUSOID_PLOT samples.
    thin+faded=input, dashed+circles=expected, solid+crosses=actual (real), dotted+plusses=actual (imag).
    Input shares the per-amplitude color but is faded (alpha=0.35) and thin.
    Markers are interleaved so overlapping lines remain distinguishable."""
    n = _N_SINUSOID_PLOT
    fig, ax = plt.subplots()
    ax.set_title(title)
    t = np.arange(n)
    for i, amp in enumerate(_SINUSOID_AMPLITUDES):
        color = f"C{i}"
        ax.plot(
            t,
            amp * unit_input[:n],
            color=color,
            alpha=0.35,
            linewidth=1.0,
            label=f"input amp={amp:.0f}",
        )
        ax.plot(
            t,
            amp * unit_reference[:n],
            linestyle="--",
            color=color,
            marker="o",
            markersize=3,
            markevery=(2, 8),
            label=f"expected amp={amp:.0f}",
        )
        ax.plot(
            t,
            actual[:n, i].real,
            linestyle="-",
            color=color,
            marker="x",
            markersize=5,
            markevery=(6, 8),
            label=f"actual amp={amp:.0f} (real)",
        )
        if np.issubdtype(dtype, np.complexfloating):
            ax.plot(
                t,
                actual[:n, i].imag,
                linestyle=":",
                color=color,
                marker="+",
                markersize=5,
                markevery=(4, 8),
                label=f"actual amp={amp:.0f} (imag)",
            )
    ax.legend()
    return fig


def _run_cold(node, input_shape: tuple, dtype: type, signal: npt.NDArray) -> npt.NDArray:
    """Run node from a cold start (no pre-warmup), return first spatial element over time."""
    outputs = [node.execute(np.full(input_shape, v, dtype=dtype)) for v in signal]
    n = len(signal)
    return np.array(outputs).reshape(n, -1)[:, 0]


def _assert_matches_reference(
    actual: npt.NDArray, expected_real: npt.NDArray, dtype: type, input_shape: tuple
) -> None:
    # Broadcast expected scalar time series over spatial dims for comparison.
    expected = np.broadcast_to(
        expected_real.reshape(len(expected_real), *(1,) * len(input_shape)),
        actual.shape,
    )
    if np.issubdtype(dtype, np.complexfloating):
        np.testing.assert_allclose(actual.real, expected, atol=1e-10, rtol=1e-6)
        np.testing.assert_allclose(actual.imag, expected, atol=1e-10, rtol=1e-6)
    else:
        np.testing.assert_allclose(actual, expected, atol=1e-10, rtol=1e-6)


def _assert_sinusoid_matches(actual: npt.NDArray, unit_reference: npt.NDArray) -> None:
    """Check actual[:, i] == _SINUSOID_AMPLITUDES[i] * unit_reference for each element."""
    for i, amp in enumerate(_SINUSOID_AMPLITUDES):
        np.testing.assert_allclose(actual[:, i], amp * unit_reference, atol=1e-10, rtol=1e-6)


def _make_tf_figure(
    plt: Any,
    title: str,
    actual: npt.NDArray,
    expected_real: npt.NDArray,
    dtype: type,
    input_signal: npt.NDArray,
) -> Any:
    fig, ax = plt.subplots()
    ax.set_title(title)
    t = np.arange(_N_TEST)
    # Extract first spatial element as a 1D time series for plotting.
    actual_1d = actual.reshape(_N_TEST, -1)[:, 0]
    ax.axvline(_N_PRE_STEP, color="gray", linestyle=":", linewidth=0.8, label="step")
    ax.plot(t, input_signal.real, color="gray", alpha=0.4, label="input")
    ax.plot(t, expected_real, label="expected (dlsim)", linestyle="--")
    ax.plot(t, actual_1d.real, label="actual (real)")
    if np.issubdtype(dtype, np.complexfloating):
        ax.plot(t, actual_1d.imag, label="actual (imag)", linestyle=":")
    ax.legend()
    return fig


def _make_warmup_figure(
    plt: Any,
    title: str,
    actual_real: npt.NDArray,
    reference: npt.NDArray,
    steady_state: float,
    input_signal: npt.NDArray,
) -> Any:
    fig, ax = plt.subplots()
    ax.set_title(title)
    t = np.arange(len(reference))
    ax.axhline(steady_state, color="gray", linestyle=":", linewidth=0.8, label="steady state")
    ax.plot(t, input_signal.real, color="gray", alpha=0.4, label="input")
    ax.plot(t, reference, label="reference (dlsim, fixed α)", linestyle="--")
    ax.plot(t, actual_real, label="actual (adaptive warmup)")
    ax.legend()
    return fig


# --- Tests ---


@pytest.mark.filterwarnings("ignore::scipy.signal.BadCoefficients")
@pytest.mark.parametrize("input_shape", _INPUT_SHAPES)
@pytest.mark.parametrize("dtype", _DTYPES)
@pytest.mark.parametrize("lp_constant", _LP_CONSTANTS)
@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
def test_step_response(
    spec: NodeSpec,
    lp_constant: float,
    dtype: type,
    input_shape: tuple,
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """Node output must match scipy.signal.dlsim using the node's transfer function."""
    alpha = lp_constant
    sys = dlti(spec.tf_num(alpha), spec.tf_den(alpha), dt=1)
    signal = _test_signal(dtype)
    expected_real = _reference_response(sys, signal)

    node = spec.cls(input_shape, np.float64(lp_constant), dtype, warmup=False)
    actual = np.array([node.execute(np.full(input_shape, v, dtype=dtype)) for v in signal])

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_tf_figure(
                plt,
                f"{spec.label} α={alpha} {dtype.__name__}",
                actual,
                expected_real,
                dtype,
                signal,
            )
        )

    _assert_matches_reference(actual, expected_real, dtype, input_shape)
    if lp_constant != 0:
        assert not np.allclose(actual.real.reshape(_N_TEST, -1)[:, 0], signal.real, atol=1e-6)


@pytest.mark.parametrize("dtype", [np.float64])
@pytest.mark.parametrize("lp_constant", _WARMUP_LP_CONSTANTS)
@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
def test_warmup_convergence(
    spec: NodeSpec,
    lp_constant: float,
    dtype: type,
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """Adaptive warmup must reach steady state faster than a cold-start fixed-α IIR."""
    alpha = lp_constant
    sys = dlti(spec.tf_num(alpha), spec.tf_den(alpha), dt=1)
    signal = _pure_step(_N_WARMUP_TEST, dtype)
    reference = _reference_response(sys, signal)

    node = spec.cls((1,), np.float64(lp_constant), dtype)
    actual = _run_cold(node, (1,), dtype, signal).real
    ss = _WARMUP_STEADY_STATE[spec.cls]

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_warmup_figure(
                plt,
                f"Warmup: {spec.label} α={alpha} {dtype.__name__}",
                actual,
                reference,
                ss,
                signal,
            )
        )

    assert np.sum((actual - ss) ** 2) < np.sum((reference - ss) ** 2)


@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
@pytest.mark.parametrize(
    "lp_constant",
    [-0.1, 1.0, 1.5, float("nan")],
    ids=["negative", "exactly-1", "above-1", "nan"],
)
def test_invalid_lp_constant_rejected(spec: NodeSpec, lp_constant: float) -> None:
    with pytest.raises(ValueError, match="lp_constant"):
        spec.cls((3,), np.float64(lp_constant), np.float64)


@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
def test_init_value_shape_mismatch_rejected(spec: NodeSpec) -> None:
    bad_init = np.zeros((4,), dtype=np.float64)
    with pytest.raises(ValueError, match="init_value"):
        spec.cls((3,), np.float64(0.5), np.float64, warmup=False, init_value=bad_init)


@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
def test_init_value_with_warmup_rejected(spec: NodeSpec) -> None:
    """init_value is meaningless under warmup — the warmup ramp overrides it on
    the first call. Constructing with both set must raise."""
    init_value = np.zeros((3,), dtype=np.float64)
    with pytest.raises(ValueError, match="warmup"):
        spec.cls((3,), np.float64(0.5), np.float64, warmup=True, init_value=init_value)


@pytest.mark.parametrize("warmup", [True, False])
def test_delayed_high_pass_first_output_is_zero(warmup: bool) -> None:
    """Without a background yet, the static part of the first input must not pass."""
    node = DelayedExponentialHighPassNode((3,), np.float64(0.5), np.complex128, warmup=warmup)

    output = node.execute(np.array([1.0 + 2.0j, -3.0, 4.0j]))

    np.testing.assert_array_equal(output, np.zeros(3))


def test_delayed_high_pass_with_warmup_subtracts_the_first_input_next() -> None:
    node = DelayedExponentialHighPassNode((3,), np.float64(0.5), np.complex128)
    first = np.array([1.0 + 2.0j, -3.0, 4.0j])
    node.execute(first)

    np.testing.assert_allclose(node.execute(first + 1.0), np.ones(3))


def test_delayed_high_pass_first_output_subtracts_init_value() -> None:
    init_value = np.array([1.0, 2.0, 3.0])
    node = DelayedExponentialHighPassNode(
        (3,), np.float64(0.5), np.float64, warmup=False, init_value=init_value
    )

    np.testing.assert_allclose(node.execute(np.array([2.0, 2.0, 2.0])), [1.0, 0.0, -1.0])


@pytest.mark.filterwarnings("ignore::scipy.signal.BadCoefficients")
@pytest.mark.parametrize("freq", _SINUSOID_FREQS)
@pytest.mark.parametrize("lp_constant", _SINUSOID_LP_CONSTANTS)
@pytest.mark.parametrize("spec", _NODE_SPECS, ids=lambda s: s.label)
def test_sinusoid_response(
    spec: NodeSpec,
    lp_constant: float,
    freq: float,
    plot_figures: list,
    plot_show_enabled: bool,
) -> None:
    """Per-element amplitude scaling must match the unit-sinusoid response (linearity)."""
    alpha = lp_constant
    sys = dlti(spec.tf_num(alpha), spec.tf_den(alpha), dt=1)
    unit_sine = np.sin(2 * np.pi * freq * np.arange(_N_TEST))
    unit_reference = _reference_response(sys, unit_sine)

    signal_array = _sinusoid_array(_N_TEST, freq)
    node = spec.cls(_SINUSOID_SHAPE, np.float64(lp_constant), np.float64, warmup=False)
    actual = np.array([node.execute(inp) for inp in signal_array])

    if plot_show_enabled:
        import matplotlib.pyplot as plt

        plot_figures.append(
            _make_sinusoid_figure(
                plt,
                f"Sinusoid: {spec.label} α={alpha} f={freq}",
                actual,
                unit_reference,
                np.float64,
                unit_sine,
            )
        )

    _assert_sinusoid_matches(actual, unit_reference)
    if lp_constant != 0:
        assert not np.allclose(actual, signal_array, atol=1e-6)
