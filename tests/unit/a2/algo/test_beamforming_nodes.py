# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for the beamforming nodes in ``_beamforming_nodes``.

Covers ``BatchConventionalBeamformNode``, which differs from
``ConventionalBeamformNode`` in that it pairs steering vectors with
covariance matrices along the leading batch axis instead of forming
their cross-product, and ``RobustCaponBeamformNode``'s eigenvalue floor
on degenerate covariance matrices.
"""

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool.a2.algo.nodes._beamforming_nodes import (
    BatchConventionalBeamformNode,
    RobustCaponBeamformNode,
)


def _random_hermitian_batch(batch: int, channels: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((batch, channels, channels)) + 1j * rng.standard_normal(
        (batch, channels, channels)
    )
    return a @ np.swapaxes(a.conj(), -1, -2)


def _random_steering(shape: tuple[int, ...], seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sv = rng.standard_normal(shape) + 1j * rng.standard_normal(shape)
    norm = np.linalg.norm(sv, axis=-1, keepdims=True)
    return sv / norm


class TestBatchConventionalBeamformNode:
    def test_output_shape_b_el(self) -> None:
        batch, channels, n_el = 5, 6, 7
        cov = _random_hermitian_batch(batch, channels, seed=10)
        sv = _random_steering((batch, n_el, channels), seed=11)
        out = BatchConventionalBeamformNode().execute(cov, sv)
        assert out.shape == (batch, n_el)
        assert out.dtype == np.float64

    def test_values_match_loop_reference(self) -> None:
        batch, channels, n_el = 4, 5, 3
        cov = _random_hermitian_batch(batch, channels, seed=20)
        sv = _random_steering((batch, n_el, channels), seed=21)

        out = BatchConventionalBeamformNode().execute(cov, sv)

        expected = np.zeros((batch, n_el), dtype=np.float64)
        for b in range(batch):
            for e in range(n_el):
                a = sv[b, e]
                expected[b, e] = float(np.real(a.conj() @ cov[b] @ a))

        np.testing.assert_allclose(out, expected, atol=1e-10)

    def test_single_batch_element(self) -> None:
        cov = _random_hermitian_batch(1, 4, seed=30)
        sv = _random_steering((1, 2, 4), seed=31)
        out = BatchConventionalBeamformNode().execute(cov, sv)
        assert out.shape == (1, 2)
        a0 = sv[0, 0]
        a1 = sv[0, 1]
        np.testing.assert_allclose(out[0, 0], float(np.real(a0.conj() @ cov[0] @ a0)))
        np.testing.assert_allclose(out[0, 1], float(np.real(a1.conj() @ cov[0] @ a1)))

    def test_multidim_steering_grid(self) -> None:
        # Steering can carry multiple inner grid dims, e.g. (B, Az, El, C).
        batch, az, el_grid, channels = 3, 4, 2, 5
        cov = _random_hermitian_batch(batch, channels, seed=40)
        sv = _random_steering((batch, az, el_grid, channels), seed=41)
        out = BatchConventionalBeamformNode().execute(cov, sv)
        assert out.shape == (batch, az, el_grid)

        # Spot-check one entry against the explicit quadratic form.
        b, a, e = 1, 2, 1
        v = sv[b, a, e]
        np.testing.assert_allclose(out[b, a, e], float(np.real(v.conj() @ cov[b] @ v)))

    def test_real_valued_output_even_for_complex_input(self) -> None:
        batch, channels, n_el = 2, 3, 4
        cov = _random_hermitian_batch(batch, channels, seed=50)
        sv = _random_steering((batch, n_el, channels), seed=51)
        out = BatchConventionalBeamformNode().execute(cov, sv)
        assert np.isrealobj(out)

    def test_raises_on_batch_mismatch(self) -> None:
        cov = _random_hermitian_batch(3, 4, seed=60)
        sv = _random_steering((4, 2, 4), seed=61)
        with pytest.raises(ValueError):
            BatchConventionalBeamformNode().execute(cov, sv)

    def test_raises_on_channel_mismatch(self) -> None:
        cov = _random_hermitian_batch(3, 4, seed=70)
        sv = _random_steering((3, 2, 5), seed=71)
        with pytest.raises(ValueError):
            BatchConventionalBeamformNode().execute(cov, sv)

    def test_raises_on_non_3d_covariance(self) -> None:
        cov = np.zeros((4, 4), dtype=np.complex128)
        sv = np.zeros((2, 4), dtype=np.complex128)
        with pytest.raises(ValueError):
            BatchConventionalBeamformNode().execute(cov, sv)

    def test_raises_on_low_rank_steering(self) -> None:
        cov = _random_hermitian_batch(2, 4, seed=80)
        sv = np.zeros((4,), dtype=np.complex128)
        with pytest.raises(ValueError):
            BatchConventionalBeamformNode().execute(cov, sv)


def _rank_one_covariance(channels: int, seed: int) -> np.ndarray:
    """A single ``(channels, channels)`` PSD covariance with rank 1:
    one positive eigenvalue, the rest exactly zero."""
    rng = np.random.default_rng(seed)
    a = rng.standard_normal(channels) + 1j * rng.standard_normal(channels)
    return np.outer(a, a.conj())


def _covariance_with_tiny_negative_eigenvalue(channels: int, seed: int) -> np.ndarray:
    """A Hermitian ``(channels, channels)`` matrix built from an explicit
    eigenbasis with one large positive eigenvalue and the rest a tiny
    negative number, mimicking the floating-point noise ``eigh`` can
    return on an operand that is only PSD in exact arithmetic."""
    rng = np.random.default_rng(seed)
    a = rng.standard_normal((channels, channels)) + 1j * rng.standard_normal((channels, channels))
    eig_vec, _ = np.linalg.qr(a)
    eig_val = np.full(channels, -1e-14)
    eig_val[0] = 1.0
    return (eig_vec * eig_val) @ eig_vec.conj().T


class TestRobustCaponBeamformNode:
    # RobustCaponBeamformNode indexes start_lambda[dist_ind, :, :], so the
    # steering grid must carry two inner (e.g. az, el) dimensions.
    def test_well_conditioned_covariance_gives_finite_output(self) -> None:
        batch, channels, n_az, n_el = 3, 4, 2, 5
        cov = _random_hermitian_batch(batch, channels, seed=100)
        sv = _random_steering((n_az, n_el, channels), seed=101)

        out = RobustCaponBeamformNode(sv, steering_vector_epsilon=0.1).execute(cov)

        assert out.shape == (batch, n_az, n_el)
        assert np.all(np.isfinite(out))

    def test_all_zero_covariance_gives_zero_output_and_freezes_start_lambda(self) -> None:
        channels, n_az, n_el = 4, 2, 3
        cov = np.zeros((1, channels, channels), dtype=np.complex128)
        sv = _random_steering((n_az, n_el, channels), seed=110)
        node = RobustCaponBeamformNode(sv, steering_vector_epsilon=0.1)
        node.start_lambda = np.full((1, n_az, n_el), 7.0)

        out = node.execute(cov)

        np.testing.assert_array_equal(out, 0.0)
        np.testing.assert_array_equal(node.start_lambda, 7.0)

    def test_rank_deficient_covariance_does_not_divide_by_zero(self) -> None:
        # Only one non-zero eigenvalue; eigh returns the rest as tiny
        # negative numbers (not exact zero), so np.min(eig_val) < 0 even
        # though np.max(eig_val) is well above the noise floor. Before
        # flooring, that negative min flipped lambda_max's sign, which
        # inverted its Newton clip bracket and produced negative output
        # power -- physically impossible for sum(|cap|^2)/sum(|cap|^2/eig_val).
        channels, n_az, n_el = 4, 2, 5
        cov = _rank_one_covariance(channels, seed=120).reshape(1, channels, channels)
        sv = _random_steering((n_az, n_el, channels), seed=121)

        out = RobustCaponBeamformNode(sv, steering_vector_epsilon=0.1).execute(cov)

        assert np.all(np.isfinite(out))
        assert np.all(out >= 0.0)

    def test_tiny_negative_eigenvalue_does_not_flip_lambda_max_sign(self) -> None:
        channels, n_az, n_el = 4, 2, 5
        cov = _covariance_with_tiny_negative_eigenvalue(channels, seed=130).reshape(
            1, channels, channels
        )
        sv = _random_steering((n_az, n_el, channels), seed=131)

        out = RobustCaponBeamformNode(sv, steering_vector_epsilon=0.1).execute(cov)

        assert np.all(np.isfinite(out))
        assert np.all(out >= 0.0)

    def test_all_zero_covariance_gives_zero_power_and_keeps_solving_afterwards(self) -> None:
        # A range bin with an all-zero covariance yields zero power and must
        # not poison the warm-started Newton solve for later frames.
        channels, n_az = 4, 5
        sv = _random_steering((n_az, 1, channels), seed=3)
        node = RobustCaponBeamformNode(steering_vectors=sv, steering_vector_epsilon=0.1)

        zero_out = node.execute(np.zeros((2, channels, channels), dtype=np.complex128))
        np.testing.assert_array_equal(zero_out, 0.0)

        cov = _random_hermitian_batch(2, channels, seed=4) + channels * np.eye(channels)
        out = node.execute(cov)
        assert out.shape == (2, n_az, 1)
        assert np.all(np.isfinite(out))
        assert np.all(out > 0.0)
