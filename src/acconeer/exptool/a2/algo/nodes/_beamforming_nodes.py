# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from typing import cast

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a2.algo.channel_covariance_matrices import (
    get_matrices_eigendecomposition,
    get_matrices_inverses,
)


def newton_vectorized_clamped(
    weights: npt.NDArray[np.float64],
    coeffs: npt.NDArray[np.float64],
    epsilon: float,
    lam_init: npt.NDArray[np.float64],
    lam_min: npt.NDArray[np.float64],
    lam_max: npt.NDArray[np.float64],
    max_iterations: int = 8,
    tolerance: float = 1e-6,
) -> npt.NDArray[np.float64]:
    """
    Helper function for robust capon beamformer.
    """
    lam = np.array(lam_init, dtype=np.float64)
    lam = np.clip(lam, lam_min, lam_max)

    for _ in range(max_iterations):
        denom = 1.0 + lam[:, :, None] * coeffs[None, None, :]
        inv_squared = weights / (denom * denom)

        g = np.sum(inv_squared, axis=2) - epsilon

        if np.max(np.abs(g)) < tolerance:
            break

        g_derivative = np.sum(-2.0 * coeffs[None, None, :] * inv_squared / denom, axis=2)
        delta = g / g_derivative

        lam_new = lam - delta
        lam = np.clip(lam_new, lam_min, lam_max)

    return lam


class CaponBeamformNode:
    """
    Performs capon beamforming on a covariance matrix (or matrices).
    """

    def __init__(self, steering_vectors: npt.NDArray[np.complex128]) -> None:
        self.steering_vectors = steering_vectors

    def execute(self, covariance_matrices: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
        # Runtime memory allocation
        out_shape = (covariance_matrices.shape[0],) + self.steering_vectors.shape[:-1]
        ids: npt.NDArray[np.complex128] = np.stack(
            [np.eye(self.steering_vectors.shape[-1], dtype=np.complex128)]
            * covariance_matrices.shape[0]
        )
        output = np.zeros(out_shape, dtype=np.float64)
        inv_matrices = get_matrices_inverses(covariance_matrices, ids)

        for idx in np.ndindex(self.steering_vectors.shape[:-1]):
            steering_vector = self.steering_vectors[idx]
            # Capon power is real-valued
            res = 1.0 / np.real(steering_vector.conj() @ inv_matrices @ steering_vector)
            output[(slice(None),) + idx] = res

        return output


class ConventionalBeamformNode:
    """
    Performs the conventional beamform on a covariance matrix (or matrices).
    """

    def __init__(self, steering_vectors: npt.NDArray[np.complex128]) -> None:
        self.steering_vectors = steering_vectors

    def execute(self, covariance_matrices: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
        out_shape = (covariance_matrices.shape[0],) + self.steering_vectors.shape[:-1]
        output = np.zeros(out_shape, dtype=np.float64)
        for idx in np.ndindex(self.steering_vectors.shape[:-1]):
            steering_vector = self.steering_vectors[idx]
            # Conventional power (B-scan) is usually the magnitude
            res = np.real(steering_vector.conj() @ covariance_matrices @ steering_vector)
            output[(slice(None),) + idx] = res

        return output


class BatchConventionalBeamformNode:
    """
    Per-batch conventional beamforming with paired covariance and steering inputs.

    Unlike :class:`ConventionalBeamformNode` (which takes a single fixed
    steering set in ``__init__`` and forms its cross-product with every batch
    covariance) this node accepts per-batch steering vectors and pairs them
    with the per-batch covariance along the leading ``B`` axis. Concretely:
    output ``b`` is computed from ``covariance_matrices[b]`` and
    ``steering_vectors[b]`` only.

    Inputs:
        covariance_matrices: shape ``(B, C, C)``. Each matrix must be
            Hermitian (``R = R^H``). :class:`CovarianceNode` guarantees
            Hermitian output by construction.
        steering_vectors:    shape ``(B, ..., C)`` -- any number of inner
            steering-grid dimensions.

    Output:
        ``(B, ...)`` real-valued power, computed as
        ``a^H R a`` where ``a`` runs over each inner steering-grid index.
        The result is real because ``R`` is required to be Hermitian.
    """

    def execute(
        self,
        covariance_matrices: npt.NDArray[np.complex128],
        steering_vectors: npt.NDArray[np.complex128],
    ) -> npt.NDArray[np.float64]:
        if covariance_matrices.ndim != 3:
            msg = f"covariance_matrices must have shape (B, C, C); got {covariance_matrices.shape}"
            raise ValueError(msg)
        if covariance_matrices.shape[1] != covariance_matrices.shape[2]:
            msg = f"covariance_matrices must be square (B, C, C); got {covariance_matrices.shape}"
            raise ValueError(msg)
        if steering_vectors.ndim < 2:
            msg = f"steering_vectors must have shape (B, ..., C); got {steering_vectors.shape}"
            raise ValueError(msg)
        if steering_vectors.shape[0] != covariance_matrices.shape[0]:
            msg = (
                "Leading batch dim mismatch: "
                f"covariance_matrices {covariance_matrices.shape[0]} vs "
                f"steering_vectors {steering_vectors.shape[0]}"
            )
            raise ValueError(msg)
        if steering_vectors.shape[-1] != covariance_matrices.shape[-1]:
            msg = (
                "Channel dim mismatch: "
                f"covariance_matrices C={covariance_matrices.shape[-1]} vs "
                f"steering_vectors C={steering_vectors.shape[-1]}"
            )
            raise ValueError(msg)

        result = np.einsum(
            "b...c,bcd,b...d->b...",
            steering_vectors.conj(),
            covariance_matrices,
            steering_vectors,
        ).real
        return cast(npt.NDArray[np.float64], result)


class DelayAndSumBeamformNode:
    """
    Performs the simple delay and sum beamform on channel data.
    """

    def __init__(self, steering_vectors: npt.NDArray[np.complex128]) -> None:
        self.steering_vectors = steering_vectors

    def execute(self, channel_data: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
        out_shape = (channel_data.shape[0],) + self.steering_vectors.shape[:-1]
        output = np.zeros(out_shape, dtype=np.complex128)
        for idx in np.ndindex(self.steering_vectors.shape[:-1]):
            steering_vector = self.steering_vectors[idx]
            # DSB usually outputs complex signal data
            res = steering_vector.conj() @ channel_data.T
            output[(slice(None),) + idx] = res
        return output


# Covariance eigenvalues below this are treated as noise floor.
_EIGENVALUE_FLOOR = 1e-20


class RobustCaponBeamformNode:
    """
    Performs robust capon beamforming using spherical uncertainty sets.
    """

    def __init__(
        self,
        steering_vectors: npt.NDArray[np.complex128],
        steering_vector_epsilon: float,
        newton_max_iterations: int = 8,
        newton_tolerance: float = 1e-6,
    ) -> None:
        self.steering_vectors = steering_vectors
        self.steering_vector_epsilon = steering_vector_epsilon
        self.start_lambda: npt.NDArray[np.float64] | None = None
        self.newton_max_iterations: int = newton_max_iterations
        self.newton_tolerance: float = newton_tolerance

    def execute(self, covariance_matrices: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64]:
        eigenvalues, eigenvectors = get_matrices_eigendecomposition(covariance_matrices)

        out_shape = (covariance_matrices.shape[0],) + self.steering_vectors.shape[:-1]
        output = np.zeros(out_shape, dtype=np.float64)

        # Setup start lambda now that we know the shape
        if self.start_lambda is None:
            self.start_lambda = np.ones(out_shape, dtype=np.float64)
        start_lambda = self.start_lambda

        for dist_ind in range(covariance_matrices.shape[0]):
            eig_val = eigenvalues[dist_ind].astype(np.float64)
            eig_vec = eigenvectors[dist_ind].astype(np.complex128)

            eig_val = np.maximum(eig_val, _EIGENVALUE_FLOOR)
            if np.max(eig_val) <= _EIGENVALUE_FLOOR:
                # Nothing above the floor: leave this bin's output at zero and keep start_lambda.
                continue

            # Robust lambda bounds calculation
            lambda_min = (1 - np.sqrt(self.steering_vector_epsilon)) / (
                np.max(eig_val) * np.sqrt(self.steering_vector_epsilon)
            )
            lambda_max = (1 - np.sqrt(self.steering_vector_epsilon)) / (
                np.min(eig_val) * np.sqrt(self.steering_vector_epsilon)
            )

            proj = self.steering_vectors @ eig_vec.conj()
            proj_ip = np.real(proj.conj() * proj).astype(np.float64)

            zeroes = newton_vectorized_clamped(
                proj_ip,
                eig_val,
                self.steering_vector_epsilon,
                start_lambda[dist_ind, :, :],
                lambda_min,
                lambda_max,
                max_iterations=self.newton_max_iterations,
                tolerance=self.newton_tolerance,
            )

            self.start_lambda[dist_ind, :, :] = zeroes

            # Intermediate CAP calculation (complex)
            cap = proj * (1 - 1 / (1 + zeroes[:, :, None] * eig_val))
            cap_ip = np.real(cap.conj() * cap)

            # Final output power calculation (real)
            output[dist_ind, :, :] = np.real(
                np.sum(cap_ip, axis=2) / np.sum(cap_ip / eig_val, axis=2)
            )

        return output
