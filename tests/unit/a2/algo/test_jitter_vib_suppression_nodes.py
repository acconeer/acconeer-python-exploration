# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for JitterAndVibrationScalingNode and its apparent-averaging helpers.

The node is stateless and pure-functional: ``execute`` reads only ``self`` config
and the inputs ``amp_per_depth``, ``temperature``. Three test groups:

1. Analytical reference (test_matches_analytical_reference)
   Re-implements the documented formula in the test using NumPy primitives plus
   ``JITTER_STD_DEG`` / ``BASE_STEP_LENGTH_M`` / ``tc_to_sf``, and asserts the
   node output matches via ``np.allclose`` over a small parameter grid.

2. Property tests
   - Zero amplitude  -> both scalings exactly 1.
   - Outputs always in (0, 1].
   - Output shape matches ``amp_per_depth.shape``.
   - Adding vibration strictly tightens both scalings.
   - Structural identity ``1/scaling**2 - 1 == c * static_dir_amp**2`` with a known
     slope c derived from the documented formula. Stronger than monotonicity:
     pins both the quadratic dependence on amplitude and the slope c, which
     encodes num_channels, apparent_avg, jitter, and vibration.
   - ``iq_averaging``: 1 is identical to leaving it out, N multiplies the
     jitter+vibration variance by ``N**(1 - efficiency)`` in both scalings.

3. Apparent-averaging helpers
   - ``iir_apparent_averaging``: pass-through filter -> 1, active filter -> > 1
     and monotonic in the time constant, re-derived against the documented
     IIR weight-sum formula.
   - ``covariance_apparent_averaging``: num_sweeps times the IIR apparent averaging.
   - Both are bit-identical to the node's former built-in ``num_sweeps / sum(w**2)``.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import (
    BASE_STEP_LENGTH_M,
    JITTER_STD_DEG,
    tc_to_sf,
)
from acconeer.exptool.a2.algo.nodes._jitter_vib_suppression_nodes import (
    _IIR_FINITE_SUM_EPSILON,
    _NEGLIGIBLE_SMOOTH_FACTOR,
    JitterAndVibrationScalingNode,
    covariance_apparent_averaging,
    delayed_high_pass_iir_apparent_averaging,
    iir_apparent_averaging,
)


# --- Constants ---

_PROFILES = [a2.Profile.PROFILE_1, a2.Profile.PROFILE_3]
_TEMPERATURES = [25.0, 50.0]  # tabulated point + between (exercises np.interp)
_VIBRATION_STDS = [0.0, 1.0]  # um
_NUM_CHANNELS = [1, 4]
_APPARENT_AVGS = [1.0, 8.0, 50.0]
_IQ_AVERAGING = [1.0, 15.0]
_UPDATE_RATE = 50.0
_NUM_POINTS = 16

# Deliberately different from the node defaults (0.1, 0.7) so the tests verify
# these parameters actually flow through to the formula instead of relying on
# the defaults matching.
_SPATIAL_UNCORR_JITTER_FACTOR = 0.15
_JITTER_AVERAGING_EFFICIENCY = 0.6


# --- Helpers ---


def _reference_iir_apparent_avg(time_const_s: float, update_rate: float) -> float:
    """Re-derivation of ``iir_apparent_averaging`` from the documented IIR weight formula."""
    sf = tc_to_sf(tc=time_const_s, fs=update_rate)
    if sf == 0.0:
        return 1.0
    finite_sum_len = int(np.round(np.log(_IIR_FINITE_SUM_EPSILON) / np.log(sf)))
    w = (1 - sf) * sf ** np.arange(finite_sum_len)
    w /= np.sum(w)
    return float(1.0 / np.sum(w**2))


def _former_apparent_avg(num_sweeps: int, time_const_s: float, update_rate: float) -> float:
    """Verbatim arithmetic of the node's former built-in apparent averaging."""
    exp_smooth_factor = tc_to_sf(tc=time_const_s, fs=update_rate)
    if exp_smooth_factor <= _NEGLIGIBLE_SMOOTH_FACTOR:
        return float(num_sweeps)
    finite_sum_len = int(np.round(np.log(_IIR_FINITE_SUM_EPSILON) / np.log(exp_smooth_factor)))
    w = (1 - exp_smooth_factor) * exp_smooth_factor ** np.arange(finite_sum_len)
    w /= np.sum(w)
    return float(num_sweeps / np.sum(w**2))


def _reference_scalings(
    profile: a2.Profile,
    vibration_std_um: float,
    num_channels: int,
    apparent_avg: float,
    iq_averaging: float,
    amp_per_depth: npt.NDArray[np.float64],
    temperature: float,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Independent re-implementation of the documented scaling formula."""
    profile_jitter = JITTER_STD_DEG[profile]
    jitter_std_deg = np.interp(
        temperature, list(profile_jitter.keys()), list(profile_jitter.values())
    )
    jitter_std_rad = float(jitter_std_deg) * np.pi / 180
    vibration_std_rad = 2.0 * np.pi * vibration_std_um * 1e-6 / BASE_STEP_LENGTH_M

    signal_power = amp_per_depth**2
    jitter_var = signal_power * (1.0 - np.exp(-(jitter_std_rad**2)))
    vibration_var = signal_power * (1.0 - np.exp(-(vibration_std_rad**2)))
    combined_var = (jitter_var + vibration_var) * iq_averaging ** (
        1 - _JITTER_AVERAGING_EFFICIENCY
    )

    subspace = np.sqrt(
        1.0
        / (1.0 + combined_var * num_channels * apparent_avg ** (1 - _JITTER_AVERAGING_EFFICIENCY))
    )
    orthogonal = 1.0 / np.sqrt(1.0 + combined_var * _SPATIAL_UNCORR_JITTER_FACTOR)
    return subspace, orthogonal


def _default_node(
    *,
    vibration_std_um: float = 1.0,
    num_channels: int = 4,
    apparent_avg: float = 8.0,
    iq_averaging: float = 1.0,
) -> JitterAndVibrationScalingNode:
    return JitterAndVibrationScalingNode(
        num_points=_NUM_POINTS,
        num_channels=num_channels,
        profile=a2.Profile.PROFILE_3,
        vibration_std_um=vibration_std_um,
        apparent_avg=apparent_avg,
        iq_averaging=iq_averaging,
        spatial_uncorr_jitter_factor=_SPATIAL_UNCORR_JITTER_FACTOR,
        jitter_averaging_efficiency=_JITTER_AVERAGING_EFFICIENCY,
    )


# --- Group 1: analytical reference ---


@pytest.mark.parametrize("profile", _PROFILES)
@pytest.mark.parametrize("temperature", _TEMPERATURES)
@pytest.mark.parametrize("vibration_std_um", _VIBRATION_STDS)
@pytest.mark.parametrize("num_channels", _NUM_CHANNELS)
@pytest.mark.parametrize("apparent_avg", _APPARENT_AVGS)
@pytest.mark.parametrize("iq_averaging", _IQ_AVERAGING)
def test_matches_analytical_reference(
    profile: a2.Profile,
    temperature: float,
    vibration_std_um: float,
    num_channels: int,
    apparent_avg: float,
    iq_averaging: float,
) -> None:
    rng = np.random.default_rng(0)
    static_dir_amp = rng.uniform(0.0, 1000.0, size=_NUM_POINTS)

    node = JitterAndVibrationScalingNode(
        num_points=_NUM_POINTS,
        num_channels=num_channels,
        profile=profile,
        vibration_std_um=vibration_std_um,
        apparent_avg=apparent_avg,
        iq_averaging=iq_averaging,
        spatial_uncorr_jitter_factor=_SPATIAL_UNCORR_JITTER_FACTOR,
        jitter_averaging_efficiency=_JITTER_AVERAGING_EFFICIENCY,
    )
    subspace, orthogonal = node.execute(amp_per_depth=static_dir_amp, temperature=temperature)

    ref_subspace, ref_orthogonal = _reference_scalings(
        profile=profile,
        vibration_std_um=vibration_std_um,
        num_channels=num_channels,
        apparent_avg=apparent_avg,
        iq_averaging=iq_averaging,
        amp_per_depth=static_dir_amp,
        temperature=temperature,
    )
    np.testing.assert_allclose(subspace, ref_subspace, rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(orthogonal, ref_orthogonal, rtol=1e-12, atol=1e-15)


# --- Group 2: property tests ---


def test_zero_signal_gives_unit_scaling() -> None:
    node = _default_node()
    static_dir_amp = np.zeros(_NUM_POINTS)
    subspace, orthogonal = node.execute(amp_per_depth=static_dir_amp, temperature=25.0)
    np.testing.assert_array_equal(subspace, np.ones(_NUM_POINTS))
    np.testing.assert_array_equal(orthogonal, np.ones(_NUM_POINTS))


def test_output_shape_matches_input() -> None:
    node = _default_node()
    static_dir_amp = np.linspace(0.0, 1000.0, _NUM_POINTS)
    subspace, orthogonal = node.execute(amp_per_depth=static_dir_amp, temperature=25.0)
    assert subspace.shape == static_dir_amp.shape
    assert orthogonal.shape == static_dir_amp.shape


def test_outputs_in_unit_interval() -> None:
    node = _default_node()
    static_dir_amp = np.linspace(0.0, 1e4, _NUM_POINTS)
    subspace, orthogonal = node.execute(amp_per_depth=static_dir_amp, temperature=25.0)
    assert np.all((subspace > 0.0) & (subspace <= 1.0))
    assert np.all((orthogonal > 0.0) & (orthogonal <= 1.0))


def test_vibration_strengthens_suppression() -> None:
    no_vib = _default_node(vibration_std_um=0.0)
    with_vib = _default_node(vibration_std_um=1.0)
    static_dir_amp = np.linspace(1.0, 100.0, _NUM_POINTS)
    sub_no, orth_no = no_vib.execute(amp_per_depth=static_dir_amp, temperature=25.0)
    sub_yes, orth_yes = with_vib.execute(amp_per_depth=static_dir_amp, temperature=25.0)
    assert np.all(sub_yes < sub_no)
    assert np.all(orth_yes < orth_no)


def test_iq_averaging_one_is_identical_to_default() -> None:
    static_dir_amp = np.linspace(0.0, 1000.0, _NUM_POINTS)
    default = JitterAndVibrationScalingNode(
        num_points=_NUM_POINTS,
        num_channels=4,
        profile=a2.Profile.PROFILE_3,
        vibration_std_um=1.0,
        apparent_avg=8.0,
        spatial_uncorr_jitter_factor=_SPATIAL_UNCORR_JITTER_FACTOR,
        jitter_averaging_efficiency=_JITTER_AVERAGING_EFFICIENCY,
    ).execute(amp_per_depth=static_dir_amp, temperature=25.0)
    explicit = _default_node(iq_averaging=1.0).execute(
        amp_per_depth=static_dir_amp, temperature=25.0
    )
    np.testing.assert_array_equal(explicit[0], default[0])
    np.testing.assert_array_equal(explicit[1], default[1])


@pytest.mark.parametrize("iq_averaging", [2.0, 15.0])
def test_iq_averaging_scales_combined_var_in_both_scalings(iq_averaging: float) -> None:
    """``1/scaling**2 - 1`` is linear in combined_var, so the ratio between
    ``iq_averaging=N`` and ``iq_averaging=1`` is ``N**(1 - efficiency)``."""
    static_dir_amp = np.linspace(1.0, 1000.0, _NUM_POINTS)
    base = _default_node().execute(amp_per_depth=static_dir_amp, temperature=25.0)
    averaged = _default_node(iq_averaging=iq_averaging).execute(
        amp_per_depth=static_dir_amp, temperature=25.0
    )
    expected_ratio = iq_averaging ** (1 - _JITTER_AVERAGING_EFFICIENCY)
    for base_scaling, averaged_scaling in zip(base, averaged):
        np.testing.assert_allclose(
            (1.0 / averaged_scaling**2 - 1.0) / (1.0 / base_scaling**2 - 1.0),
            expected_ratio,
            rtol=1e-9,
        )


@pytest.mark.parametrize("num_channels", _NUM_CHANNELS)
@pytest.mark.parametrize("apparent_avg", _APPARENT_AVGS)
@pytest.mark.parametrize("vibration_std_um", _VIBRATION_STDS)
def test_inverse_square_minus_one_linear_in_signal_power(
    num_channels: int,
    apparent_avg: float,
    vibration_std_um: float,
) -> None:
    """``1/scaling**2 - 1 == c * static_dir_amp**2`` with c derived from config.

    Pins both functional form (quadratic in amplitude) and the slope c, which
    encodes num_channels, apparent_avg, jitter, and vibration. Stronger than
    monotonicity and subsumes the (0, 1] / zero-input invariants."""
    profile = a2.Profile.PROFILE_3
    temperature = 25.0
    num_points = 50
    node = JitterAndVibrationScalingNode(
        num_points=num_points,
        num_channels=num_channels,
        profile=profile,
        vibration_std_um=vibration_std_um,
        apparent_avg=apparent_avg,
        spatial_uncorr_jitter_factor=_SPATIAL_UNCORR_JITTER_FACTOR,
        jitter_averaging_efficiency=_JITTER_AVERAGING_EFFICIENCY,
    )
    static_dir_amp = np.linspace(0.0, 1000.0, num_points)
    subspace, orthogonal = node.execute(amp_per_depth=static_dir_amp, temperature=temperature)

    profile_jitter = JITTER_STD_DEG[profile]
    jitter_std_deg = np.interp(
        temperature, list(profile_jitter.keys()), list(profile_jitter.values())
    )
    jitter_std_rad = float(jitter_std_deg) * np.pi / 180
    vibration_std_rad = 2.0 * np.pi * vibration_std_um * 1e-6 / BASE_STEP_LENGTH_M
    k = (1.0 - np.exp(-(jitter_std_rad**2))) + (1.0 - np.exp(-(vibration_std_rad**2)))
    c_sub = k * num_channels * apparent_avg ** (1 - _JITTER_AVERAGING_EFFICIENCY)
    c_orth = k * _SPATIAL_UNCORR_JITTER_FACTOR

    np.testing.assert_allclose(
        1.0 / subspace**2 - 1.0, c_sub * static_dir_amp**2, rtol=1e-10, atol=1e-12
    )
    np.testing.assert_allclose(
        1.0 / orthogonal**2 - 1.0, c_orth * static_dir_amp**2, rtol=1e-10, atol=1e-12
    )


# --- Group 3: apparent-averaging helpers ---


def test_iir_apparent_averaging_no_lp_filter() -> None:
    """time_const_s = 0 -> tc_to_sf returns 0 -> a single sample is averaged."""
    assert iir_apparent_averaging(time_const_s=0.0, update_rate=_UPDATE_RATE) == 1.0


def test_iir_apparent_averaging_exceeds_one_and_is_monotonic() -> None:
    apparent_avgs = [
        iir_apparent_averaging(time_const_s=tc, update_rate=_UPDATE_RATE)
        for tc in [0.01, 0.05, 0.2]
    ]
    assert all(a > 1.0 for a in apparent_avgs)
    assert apparent_avgs == sorted(apparent_avgs)


@pytest.mark.parametrize("time_const_s", [0.0, 0.01, 0.1, 3.0])
def test_iir_apparent_averaging_matches_reference_formula(time_const_s: float) -> None:
    expected = _reference_iir_apparent_avg(time_const_s=time_const_s, update_rate=_UPDATE_RATE)
    assert iir_apparent_averaging(
        time_const_s=time_const_s, update_rate=_UPDATE_RATE
    ) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("high_pass_time_const_s", [0.0, 0.3, 1.0, 5.0])
@pytest.mark.parametrize("time_const_s", [0.0, 0.5, 2.0])
def test_delayed_high_pass_apparent_averaging_matches_the_correlation_series(
    high_pass_time_const_s: float, time_const_s: float
) -> None:
    a = tc_to_sf(high_pass_time_const_s, _UPDATE_RATE)
    b = tc_to_sf(time_const_s, _UPDATE_RATE)
    lags = np.arange(1, 5000)
    rho = -(1 - a) / 2 * a ** (lags - 1)
    inflation = 1 + 2 * np.sum(rho**2 * b**lags)
    expected = iir_apparent_averaging(time_const_s, _UPDATE_RATE) / inflation

    actual = delayed_high_pass_iir_apparent_averaging(
        high_pass_time_const_s, time_const_s, _UPDATE_RATE
    )

    assert actual == pytest.approx(expected, rel=1e-9)


def test_delayed_high_pass_apparent_averaging_matches_monte_carlo() -> None:
    """Frame-to-frame subtraction of complex white noise, then an exponential
    average of ``|y|**2``: its spread gives the actual degrees of freedom."""
    update_rate = 8.0
    time_const_s = 2.0
    b = tc_to_sf(time_const_s, update_rate)
    rng = np.random.default_rng(0)
    x = (rng.standard_normal((300, 20000)) + 1j * rng.standard_normal((300, 20000))) / np.sqrt(2)
    y = (x[1:] - x[:-1]) / np.sqrt(2)
    estimate = np.zeros(x.shape[1])
    for n, frame in enumerate(np.abs(y) ** 2):
        sf = min(b, n / (n + 1))
        estimate = sf * estimate + (1 - sf) * frame

    dof = np.mean(estimate) ** 2 / np.var(estimate)

    expected = delayed_high_pass_iir_apparent_averaging(0.0, time_const_s, update_rate)
    assert dof == pytest.approx(expected, rel=0.05)
    assert dof < 0.75 * iir_apparent_averaging(time_const_s, update_rate)


@pytest.mark.parametrize("num_sweeps", [1, 8, 15])
@pytest.mark.parametrize("time_const_s", [0.0, 0.15, 3.0])
def test_covariance_apparent_averaging_matches_reference_formula(
    num_sweeps: int, time_const_s: float
) -> None:
    expected = num_sweeps * _reference_iir_apparent_avg(
        time_const_s=time_const_s, update_rate=_UPDATE_RATE
    )
    assert covariance_apparent_averaging(
        num_sweeps=num_sweeps, time_const_s=time_const_s, update_rate=_UPDATE_RATE
    ) == (pytest.approx(expected, rel=1e-12))


@pytest.mark.parametrize("update_rate", [5.0, 6.0, 10.0, 13.0, 50.0, 80.0])
@pytest.mark.parametrize("time_const_s", [0.0, 0.01, 0.05, 0.15, 0.3, 1.0, 3.0, 7.5])
def test_apparent_averaging_bit_identical_to_former_formula(
    time_const_s: float, update_rate: float
) -> None:
    assert iir_apparent_averaging(
        time_const_s=time_const_s, update_rate=update_rate
    ) == _former_apparent_avg(num_sweeps=1, time_const_s=time_const_s, update_rate=update_rate)
    for num_sweeps in range(1, 65):
        assert covariance_apparent_averaging(
            num_sweeps=num_sweeps, time_const_s=time_const_s, update_rate=update_rate
        ) == _former_apparent_avg(
            num_sweeps=num_sweeps, time_const_s=time_const_s, update_rate=update_rate
        ), num_sweeps


@pytest.mark.parametrize("kwargs", [{"apparent_avg": 0.5}, {"iq_averaging": 0.5}])
def test_node_rejects_averaging_less_than_one(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        _default_node(**kwargs)


# --- Group 4: temperature clamping outside the jitter table ---
#
# np.interp clamps to the endpoint value when temperature is outside [xp.min, xp.max].
# Locks in this behavior so a future refactor (e.g. switching to a different
# interpolator) cannot silently extrapolate.


def test_temperature_below_table_clamps_to_min() -> None:
    """Temperature below the lowest tabulated point uses the lowest tabulated jitter."""
    node = _default_node()
    static_dir_amp = np.linspace(1.0, 100.0, _NUM_POINTS)
    min_temp = min(JITTER_STD_DEG[node.profile].keys())
    out_below = node.execute(amp_per_depth=static_dir_amp, temperature=float(min_temp) - 100.0)
    out_at_min = node.execute(amp_per_depth=static_dir_amp, temperature=float(min_temp))
    np.testing.assert_allclose(out_below[0], out_at_min[0])
    np.testing.assert_allclose(out_below[1], out_at_min[1])


def test_temperature_above_table_clamps_to_max() -> None:
    """Temperature above the highest tabulated point uses the highest tabulated jitter."""
    node = _default_node()
    static_dir_amp = np.linspace(1.0, 100.0, _NUM_POINTS)
    max_temp = max(JITTER_STD_DEG[node.profile].keys())
    out_above = node.execute(amp_per_depth=static_dir_amp, temperature=float(max_temp) + 100.0)
    out_at_max = node.execute(amp_per_depth=static_dir_amp, temperature=float(max_temp))
    np.testing.assert_allclose(out_above[0], out_at_max[0])
    np.testing.assert_allclose(out_above[1], out_at_max[1])
