# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""
Unit tests for SubspaceScalingOverCovNode and SubspaceScalingOverSweepsNode.

Both nodes build the same Hermitian projection matrix per distance d:

    u_d = rank_one_subspaces[d] / ||rank_one_subspaces[d]||
    P_d = c_orth[d] * (I - u_d u_d^H) + c_sub[d] * (u_d u_d^H)

The Cov node returns  P R P  (per distance); the Sweeps node returns  P x  for
every sweep x at distance d. Because P is Hermitian, the identity
    cov(P x) = P cov(x) P^H = P R P
links the two operations.

Test groups (covering both nodes unless noted):

1. Shape validation — each guard raises ValueError.
2. Identity scaling (c_sub=c_orth=1) — output equals input.
3. Uniform scaling (c_sub=c_orth=c) — Cov: c^2 R; Sweeps: c x.
4. Pure subspace projector (c_sub=1, c_orth=0): P = u u^H.
       Cov: P R P = (u^H R u) u u^H.   Sweeps: P x = (u^H x) u.
5. Pure orthogonal projector (c_sub=0, c_orth=1): P = I - u u^H.
       Cov: P R P = 0 when R = u u^H.   Sweeps: P u = 0.
6. Hermitian/PSD preservation (Cov only).
7. Normalization independence — rescaling u does not change the output.
8. Zero subspace direction — P collapses to c_orth * I.
9. Per-distance independence — perturbing one distance leaves the others unchanged.
10. Cross-node consistency — empirical cov of projected sweeps equals Cov node output.

StaticDirectionAmplitudeNode, the amplitude along the same direction u, is
tested at the end.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from acconeer.exptool.a2.algo.nodes._subspace_scaling_nodes import (
    StaticDirectionAmplitudeNode,
    SubspaceScalingOverCovNode,
    SubspaceScalingOverSweepsNode,
)


# --- Constants ---

_NUM_POINTS = 3
_NUM_CHANNELS = 4
_NUM_SWEEPS = 5
_RTOL = 1e-10
_ATOL = 1e-12


# --- Helpers ---


def _rng() -> np.random.Generator:
    return np.random.default_rng(0)


def _hermitian_psd_R(rng: np.random.Generator) -> npt.NDArray[np.complex128]:
    """Random Hermitian PSD covariance, shape (num_points, num_channels, num_channels)."""
    a = rng.standard_normal(
        (_NUM_POINTS, _NUM_CHANNELS, _NUM_CHANNELS)
    ) + 1j * rng.standard_normal((_NUM_POINTS, _NUM_CHANNELS, _NUM_CHANNELS))
    return (a @ np.conjugate(a.swapaxes(-1, -2))).astype(np.complex128)


def _complex_u(rng: np.random.Generator) -> npt.NDArray[np.complex128]:
    """Random complex subspace directions, shape (num_points, num_channels) — not unit-normalized."""
    return (
        rng.standard_normal((_NUM_POINTS, _NUM_CHANNELS))
        + 1j * rng.standard_normal((_NUM_POINTS, _NUM_CHANNELS))
    ).astype(np.complex128)


def _complex_sweeps(rng: np.random.Generator) -> npt.NDArray[np.complex128]:
    """Random complex sweeps, shape (num_sweeps, num_points, num_channels)."""
    return (
        rng.standard_normal((_NUM_SWEEPS, _NUM_POINTS, _NUM_CHANNELS))
        + 1j * rng.standard_normal((_NUM_SWEEPS, _NUM_POINTS, _NUM_CHANNELS))
    ).astype(np.complex128)


def _normalize(u: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
    norms = np.linalg.norm(u, axis=1, keepdims=True)
    return (u / norms).astype(np.complex128)


def _cov_node() -> SubspaceScalingOverCovNode:
    return SubspaceScalingOverCovNode(_NUM_POINTS, _NUM_CHANNELS)


def _sweeps_node() -> SubspaceScalingOverSweepsNode:
    return SubspaceScalingOverSweepsNode(_NUM_POINTS, _NUM_SWEEPS, _NUM_CHANNELS)


def _ones() -> npt.NDArray[np.float64]:
    return np.ones(_NUM_POINTS, dtype=np.float64)


def _zeros() -> npt.NDArray[np.float64]:
    return np.zeros(_NUM_POINTS, dtype=np.float64)


def _random_scalings(
    rng: np.random.Generator,
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    c_sub = rng.uniform(0.0, 3.0, size=_NUM_POINTS).astype(np.float64)
    c_orth = rng.uniform(0.0, 3.0, size=_NUM_POINTS).astype(np.float64)
    return c_sub, c_orth


# --- Group 1: Shape validation ---
#
# execute() guards each input by shape. The parametrized cases below mutate one
# argument to a deliberately wrong shape (extra row, extra column, extra point)
# while keeping the others valid, and assert that ValueError fires with a
# message mentioning the offending argument's name. Catches both a missing
# guard and a guard whose error message would be unclear.


_BAD_COV_INPUTS = [
    ("covariance_matrices", (_NUM_POINTS, _NUM_CHANNELS + 1, _NUM_CHANNELS)),
    ("rank_one_subspaces", (_NUM_POINTS, _NUM_CHANNELS + 1)),
    ("subspace_scaling", (_NUM_POINTS + 1,)),
    ("orthogonal_scaling", (_NUM_POINTS + 1,)),
]


@pytest.mark.parametrize(("arg_name", "bad_shape"), _BAD_COV_INPUTS)
def test_cov_node_shape_validation(arg_name: str, bad_shape: tuple) -> None:
    rng = _rng()
    args: dict[str, npt.NDArray] = {
        "covariance_matrices": _hermitian_psd_R(rng),
        "rank_one_subspaces": _complex_u(rng),
        "subspace_scaling": _ones(),
        "orthogonal_scaling": _ones(),
    }
    if arg_name in ("covariance_matrices", "rank_one_subspaces"):
        args[arg_name] = np.zeros(bad_shape, dtype=np.complex128)
    else:
        args[arg_name] = np.zeros(bad_shape, dtype=np.float64)
    with pytest.raises(ValueError, match=arg_name):
        _cov_node().execute(**args)


_BAD_SWEEPS_INPUTS = [
    ("sweeps", (_NUM_SWEEPS + 1, _NUM_POINTS, _NUM_CHANNELS)),
    ("rank_one_subspaces", (_NUM_POINTS, _NUM_CHANNELS + 1)),
    ("subspace_scaling", (_NUM_POINTS + 1,)),
    ("orthogonal_scaling", (_NUM_POINTS + 1,)),
]


@pytest.mark.parametrize(("arg_name", "bad_shape"), _BAD_SWEEPS_INPUTS)
def test_sweeps_node_shape_validation(arg_name: str, bad_shape: tuple) -> None:
    rng = _rng()
    args: dict[str, npt.NDArray] = {
        "sweeps": _complex_sweeps(rng),
        "rank_one_subspaces": _complex_u(rng),
        "subspace_scaling": _ones(),
        "orthogonal_scaling": _ones(),
    }
    if arg_name in ("sweeps", "rank_one_subspaces"):
        args[arg_name] = np.zeros(bad_shape, dtype=np.complex128)
    else:
        args[arg_name] = np.zeros(bad_shape, dtype=np.float64)
    with pytest.raises(ValueError, match=arg_name):
        _sweeps_node().execute(**args)


# --- Group 2: Identity scaling (c_sub = c_orth = 1) ---
#
# With c_sub = c_orth = 1 the projection collapses to P = (I - uu^H) + uu^H = I
# regardless of u. Output must equal input exactly. This is the cheapest sanity
# check — any sign, conjugation, or matmul mistake in constructing P breaks it.


def test_cov_node_identity_scaling_returns_input() -> None:
    """P = I for any u, so P R P = R."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    out = _cov_node().execute(R, u, _ones(), _ones())
    np.testing.assert_allclose(out, R, atol=_ATOL, rtol=_RTOL)


def test_sweeps_node_identity_scaling_returns_input() -> None:
    """P = I for any u, so P x = x for every sweep."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    out = _sweeps_node().execute(sweeps, u, _ones(), _ones())
    np.testing.assert_allclose(out, sweeps, atol=_ATOL, rtol=_RTOL)


# --- Group 3: Uniform scaling (c_sub = c_orth = c) ---
#
# Setting both scalings to the same value c reduces P to the scalar matrix
# P = c · I. Output is then c^2 · R (Cov) or c · x (Sweeps). One step up from
# identity: catches bugs where the subspace and orthogonal scalings are
# combined the wrong way (e.g. via addition instead of weighted projection).


def test_cov_node_uniform_scaling() -> None:
    """P = c * I, so P R P = c^2 R."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    c = 2.5
    scaling = _ones() * c
    out = _cov_node().execute(R, u, scaling, scaling)
    np.testing.assert_allclose(out, (c**2) * R, atol=_ATOL, rtol=_RTOL)


def test_sweeps_node_uniform_scaling() -> None:
    """P = c * I, so P x = c x."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    c = 2.5
    scaling = _ones() * c
    out = _sweeps_node().execute(sweeps, u, scaling, scaling)
    np.testing.assert_allclose(out, c * sweeps, atol=_ATOL, rtol=_RTOL)


# --- Group 4: Pure subspace projector (c_sub=1, c_orth=0) ---
#
# With c_sub=1, c_orth=0 the projection becomes the rank-1 orthogonal projector
# onto span(u): P = u u^H. Outputs have closed forms — (u^H R u) · u u^H for
# Cov, (u^H x) · u for Sweeps — checked against random Hermitian PSD R and
# random complex sweeps. Because inputs are complex, a missing conjugation
# (u^T instead of u^H) would show up here even though it is invisible in the
# real case.


def test_cov_node_pure_subspace_projector() -> None:
    """P = u u^H, so P R P = (u^H R u) u u^H per distance."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _normalize(_complex_u(rng))
    out = _cov_node().execute(R, u, _ones(), _zeros())

    expected = np.empty_like(out)
    for d in range(_NUM_POINTS):
        scalar = np.conjugate(u[d]) @ R[d] @ u[d]
        expected[d] = scalar * np.outer(u[d], np.conjugate(u[d]))
    np.testing.assert_allclose(out, expected, atol=1e-10, rtol=_RTOL)


def test_sweeps_node_pure_subspace_projector() -> None:
    """P = u u^H, so P x = (u^H x) u per distance per sweep."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _normalize(_complex_u(rng))
    out = _sweeps_node().execute(sweeps, u, _ones(), _zeros())

    # scalars[s, d] = u[d]^H @ sweeps[s, d]
    scalars = np.einsum("dc,sdc->sd", np.conjugate(u), sweeps)
    expected = scalars[..., None] * u[None, :, :]
    np.testing.assert_allclose(out, expected, atol=1e-10, rtol=_RTOL)


# --- Group 5: Pure orthogonal projector (c_sub=0, c_orth=1) ---
#
# With c_sub=0, c_orth=1 the projection becomes the rank-(N-1) projector onto
# the orthogonal complement of u: P = I - u u^H. By choosing inputs that lie
# entirely inside span(u) — R = u u^H, or every sweep equal to u — the
# expected output is exactly zero, giving the strictest possible assertion.
# Pins down both the construction of P and the sign of the subtraction.


def test_cov_node_pure_orthogonal_projector_annihilates_subspace() -> None:
    """P = I - u u^H annihilates u, so P (u u^H) P = 0."""
    rng = _rng()
    u = _normalize(_complex_u(rng))
    R = np.array(
        [np.outer(u[d], np.conjugate(u[d])) for d in range(_NUM_POINTS)],
        dtype=np.complex128,
    )
    out = _cov_node().execute(R, u, _zeros(), _ones())
    np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-10)


def test_sweeps_node_pure_orthogonal_projector_annihilates_subspace() -> None:
    """P = I - u u^H, so P u = 0; sweeps equal to u project to 0."""
    rng = _rng()
    u = _normalize(_complex_u(rng))
    # Every sweep at distance d equals u[d] (broadcast across sweeps).
    sweeps = np.broadcast_to(u, (_NUM_SWEEPS, _NUM_POINTS, _NUM_CHANNELS)).astype(np.complex128)
    out = _sweeps_node().execute(sweeps, u, _zeros(), _ones())
    np.testing.assert_allclose(out, np.zeros_like(out), atol=1e-10)


# --- Group 6: Hermitian/PSD preservation (Cov node only) ---
#
# For Hermitian PSD R, Hermitian P, and non-negative scalings, the product
# P R P must remain Hermitian and positive semi-definite. The test checks
# Hermitian-ness directly (out[d] == out[d]^H) and PSD via the smallest
# eigenvalue using np.linalg.eigvalsh (valid because out[d] is Hermitian).
# A bug that drops a conjugate inside the projection matmul would produce an
# asymmetric output with negative eigenvalues — both assertions catch that.


def test_cov_node_preserves_hermitian_and_psd() -> None:
    """Hermitian PSD input with non-negative scalings yields Hermitian PSD output."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)
    out = _cov_node().execute(R, u, c_sub, c_orth)

    for d in range(_NUM_POINTS):
        np.testing.assert_allclose(
            out[d], np.conjugate(out[d].T), atol=1e-10, err_msg=f"d={d} not Hermitian"
        )
        eigs = np.linalg.eigvalsh(out[d])
        assert eigs.min() > -1e-9, f"d={d} not PSD, min eig = {eigs.min()}"


# --- Group 7: Normalization independence ---
#
# The node normalizes the subspace direction internally before building P, so
# the API accepts any nonzero u. Multiplying u[d] by any nonzero complex factor
# (magnitude AND phase) must leave the output unchanged. Using a complex
# rescale — not just real — is important: it catches a bug where the node
# normalizes by |u| but leaves a residual phase, producing a different P.


def _random_complex_scales(rng: np.random.Generator) -> npt.NDArray[np.complex128]:
    """Per-distance nonzero complex scaling factor with random magnitude and phase."""
    return (
        rng.uniform(0.1, 5.0, size=_NUM_POINTS)
        * np.exp(1j * rng.uniform(0, 2 * np.pi, size=_NUM_POINTS))
    ).astype(np.complex128)


def test_cov_node_normalization_independence() -> None:
    """Output is invariant to per-distance nonzero complex rescaling of u."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)
    u_scaled = (u * _random_complex_scales(rng)[:, None]).astype(np.complex128)

    out_a = _cov_node().execute(R, u, c_sub, c_orth)
    out_b = _cov_node().execute(R, u_scaled, c_sub, c_orth)
    np.testing.assert_allclose(out_a, out_b, atol=1e-10, rtol=1e-10)


def test_sweeps_node_normalization_independence() -> None:
    """Output is invariant to per-distance nonzero complex rescaling of u."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)
    u_scaled = (u * _random_complex_scales(rng)[:, None]).astype(np.complex128)

    out_a = _sweeps_node().execute(sweeps, u, c_sub, c_orth)
    out_b = _sweeps_node().execute(sweeps, u_scaled, c_sub, c_orth)
    np.testing.assert_allclose(out_a, out_b, atol=1e-10, rtol=1e-10)


# --- Group 8: Zero subspace direction ---
#
# Exercises the _DIV_BY_ZERO_LIMIT branch in the source. When ||u[d]|| is below
# the limit the node treats the subspace as undefined, drops the rank-1
# contribution, and P[d] reduces to c_orth[d] · I. The tests set u[0] = 0,
# leave the other distances populated with valid u, and assert that distance 0
# matches the fallback algebra exactly — that the branch is taken AND that the
# reduced formula is correct.


def test_cov_node_zero_subspace_direction_falls_back_to_orthogonal_scaling() -> None:
    """||u[d]||~0 ⇒ P[d] = c_orth[d] * I ⇒ output[d] = c_orth[d]^2 * R[d]."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    u[0] = 0
    c_sub = np.array([1.5, 2.0, 0.5], dtype=np.float64)
    c_orth = np.array([3.0, 1.0, 2.0], dtype=np.float64)

    out = _cov_node().execute(R, u, c_sub, c_orth)
    np.testing.assert_allclose(out[0], (c_orth[0] ** 2) * R[0], atol=_ATOL, rtol=_RTOL)


def test_sweeps_node_zero_subspace_direction_falls_back_to_orthogonal_scaling() -> None:
    """||u[d]||~0 ⇒ P[d] = c_orth[d] * I ⇒ output[s, d] = c_orth[d] * sweeps[s, d]."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    u[0] = 0
    c_sub = np.array([1.5, 2.0, 0.5], dtype=np.float64)
    c_orth = np.array([3.0, 1.0, 2.0], dtype=np.float64)

    out = _sweeps_node().execute(sweeps, u, c_sub, c_orth)
    np.testing.assert_allclose(out[:, 0, :], c_orth[0] * sweeps[:, 0, :], atol=_ATOL, rtol=_RTOL)


# --- Group 9: Per-distance independence ---
#
# Each distance is processed with its own P[d]; nothing should leak across
# distances. The tests mutate inputs at d=0 only and assert that outputs at
# d>=1 are unchanged. A second "not allclose at d=0" assertion guards against
# the trivial case where the mutation happened to have no effect (which would
# pass the first check vacuously). Catches einsum-subscript or axis-ordering
# bugs that would mix distances — exactly the kind of mistake that is silent
# in shape-correct tests like the identity check.


def test_cov_node_per_distance_independence() -> None:
    """Perturbing R at d=0 only must leave outputs at d>=1 unchanged."""
    rng = _rng()
    R = _hermitian_psd_R(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)

    out_a = _cov_node().execute(R, u, c_sub, c_orth)

    R_mod = R.copy()
    R_mod[0] = R_mod[0] + np.eye(_NUM_CHANNELS) * 7.0
    R_mod[0] = 0.5 * (R_mod[0] + np.conjugate(R_mod[0].T))
    out_b = _cov_node().execute(R_mod, u, c_sub, c_orth)

    np.testing.assert_allclose(out_a[1:], out_b[1:], atol=_ATOL, rtol=_RTOL)
    assert not np.allclose(out_a[0], out_b[0])


def test_sweeps_node_per_distance_independence() -> None:
    """Perturbing sweeps at d=0 only must leave outputs at d>=1 unchanged."""
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)

    out_a = _sweeps_node().execute(sweeps, u, c_sub, c_orth)

    sweeps_mod = sweeps.copy()
    sweeps_mod[:, 0, :] += 10.0 + 3.0j
    out_b = _sweeps_node().execute(sweeps_mod, u, c_sub, c_orth)

    np.testing.assert_allclose(out_a[:, 1:, :], out_b[:, 1:, :], atol=_ATOL, rtol=_RTOL)
    assert not np.allclose(out_a[:, 0, :], out_b[:, 0, :])


# --- Group 10: Cross-node consistency ---
#
# The most end-to-end check: the two nodes are linked by the identity
#     cov(P x) = P cov(x) P^H = P R P   (P is Hermitian)
# Given the same parameters, the empirical covariance of the projected sweeps
# returned by the Sweeps node must equal the Cov node applied to the empirical
# covariance of the original sweeps. A bug in only one of the two nodes will
# break this equality — even if that node's other test groups all pass.


def test_sweeps_and_cov_nodes_are_consistent() -> None:
    """cov(P x) = P cov(x) P^H = P R P (P is Hermitian).

    Apply the Sweeps node to a set of sweeps, then form the empirical covariance
    of the projected sweeps. It must equal the Cov node output on the empirical
    covariance of the original sweeps.
    """
    rng = _rng()
    sweeps = _complex_sweeps(rng)
    u = _complex_u(rng)
    c_sub, c_orth = _random_scalings(rng)

    # Empirical covariance: R[d,i,j] = (1/N) Σ_s sweeps[s,d,i] * conj(sweeps[s,d,j])
    R_emp = (np.einsum("sdi,sdj->dij", sweeps, np.conjugate(sweeps)) / _NUM_SWEEPS).astype(
        np.complex128
    )

    projected = _sweeps_node().execute(sweeps, u, c_sub, c_orth)
    y_cov_emp = np.einsum("sdi,sdj->dij", projected, np.conjugate(projected)) / _NUM_SWEEPS

    r_out = _cov_node().execute(R_emp, u, c_sub, c_orth)

    np.testing.assert_allclose(y_cov_emp, r_out, atol=1e-10, rtol=1e-8)


# --- StaticDirectionAmplitudeNode ---


class TestStaticDirectionAmplitudeNode:
    def _static(self) -> npt.NDArray[np.complex128]:
        rng = _rng()
        return rng.standard_normal((_NUM_POINTS, _NUM_CHANNELS)) + 1j * rng.standard_normal(
            (_NUM_POINTS, _NUM_CHANNELS)
        )

    def _orthogonal_to(self, static: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        """A signal orthogonal to ``static`` at every range point."""
        other = _rng().standard_normal((_NUM_POINTS, _NUM_CHANNELS)) + 0j
        unit = static / np.linalg.norm(static, axis=1, keepdims=True)
        orthogonal = other - np.sum(np.conj(unit) * other, axis=1, keepdims=True) * unit
        assert np.all(np.linalg.norm(orthogonal, axis=1) > 0.1)
        return orthogonal

    def test_coherent_static_reflector_gives_rms_per_channel_amplitude(self) -> None:
        static = self._static()
        sweep = (0.5 - 2.0j) * static

        amplitude = StaticDirectionAmplitudeNode().execute(static=static, sweep=sweep)

        assert amplitude.dtype == np.float64
        rms = np.sqrt(np.mean(np.abs(sweep) ** 2, axis=1))
        np.testing.assert_allclose(amplitude, rms, rtol=_RTOL)

    def test_signal_orthogonal_to_the_static_direction_does_not_add(self) -> None:
        static = self._static()
        orthogonal = self._orthogonal_to(static)
        static_part = (0.5 - 2.0j) * static
        node = StaticDirectionAmplitudeNode()

        orthogonal_only = node.execute(static=static, sweep=orthogonal)
        mixed = node.execute(static=static, sweep=static_part + 10.0 * orthogonal)

        np.testing.assert_allclose(orthogonal_only, 0.0, atol=_ATOL)
        static_part_rms = np.sqrt(np.mean(np.abs(static_part) ** 2, axis=1))
        np.testing.assert_allclose(mixed, static_part_rms, rtol=_RTOL)

    def test_zero_static_gives_zero(self) -> None:
        static = self._static()
        static[1] = 0.0

        amplitude = StaticDirectionAmplitudeNode().execute(static=static, sweep=self._static())

        assert amplitude[1] == 0.0
        assert np.all(amplitude[[0, 2]] > 0.0)

    def test_rejects_mismatched_shapes(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            StaticDirectionAmplitudeNode().execute(
                static=np.zeros((_NUM_POINTS, _NUM_CHANNELS), dtype=np.complex128),
                sweep=np.zeros((_NUM_POINTS, _NUM_CHANNELS + 1), dtype=np.complex128),
            )
