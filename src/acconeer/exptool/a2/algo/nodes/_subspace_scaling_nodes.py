# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import numpy as np
import numpy.typing as npt


_DIV_BY_ZERO_LIMIT: float = 1e-12


def _unit_directions(vectors: npt.NDArray[np.complex128]) -> npt.NDArray[np.complex128]:
    """``vectors[d] / ||vectors[d]||`` per distance d, and zero where
    ``||vectors[d]|| <= _DIV_BY_ZERO_LIMIT`` leaves the direction undefined."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    valid = norms > _DIV_BY_ZERO_LIMIT
    safe_norms = np.where(valid, norms, 1.0)
    return np.asarray(np.where(valid, vectors / safe_norms, 0.0), dtype=np.complex128)


def _build_projection_matrices(
    rank_one_subspaces: npt.NDArray[np.complex128],
    subspace_scaling: npt.NDArray[np.float64],
    orthogonal_scaling: npt.NDArray[np.float64],
    num_channels: int,
) -> npt.NDArray[np.complex128]:
    """Hermitian projection matrix per distance.

    For each distance d:
        u_d = rank_one_subspaces[d] / ||rank_one_subspaces[d]||
        P[d] = c_orth[d] * (I - u_d u_d^H)  +  c_sub[d] * (u_d u_d^H)

    When ``||rank_one_subspaces[d]|| <= _DIV_BY_ZERO_LIMIT`` the subspace is
    treated as undefined and the rank-1 contribution drops, leaving
    ``P[d] = c_orth[d] * I``.
    """
    unit_subspaces = _unit_directions(rank_one_subspaces)

    # uu_h[d] = u_d  u_d^H  (rank-1 subspace matrix)
    uu_h = unit_subspaces[:, :, None] @ np.conjugate(unit_subspaces[:, None, :])

    eye = np.eye(num_channels)
    return np.asarray(
        (eye - uu_h) * orthogonal_scaling[:, None, None] + uu_h * subspace_scaling[:, None, None],
        dtype=np.complex128,
    )


class StaticDirectionAmplitudeNode:
    """Amplitude of a sweep along the static direction, per range point.

    With ``u = static / ||static||`` the unit static direction at a range
    point, the amplitude is ``|u^H x| / sqrt(num_channels)`` for the sweep
    ``x`` there. For a coherent static reflector this equals its per-channel
    amplitude (RMS over channels). Where the static direction is undefined
    (``||static|| <= _DIV_BY_ZERO_LIMIT``, as in the projection) it is 0.
    """

    def execute(
        self,
        static: npt.NDArray[np.complex128],
        sweep: npt.NDArray[np.complex128],
    ) -> npt.NDArray[np.float64]:
        """
        :param static: Static estimate per range point, shape (num_points, num_channels).
        :param sweep: Sweep per range point, shape (num_points, num_channels).
        :returns: Amplitude along the static direction, shape (num_points,).
        """
        if static.shape != sweep.shape or static.ndim != 2:
            msg = (
                "static and sweep must share one (num_points, num_channels) shape; "
                f"got {static.shape} and {sweep.shape}"
            )
            raise ValueError(msg)
        unit = _unit_directions(static)
        return np.asarray(
            np.abs(np.sum(np.conj(unit) * sweep, axis=1)) / np.sqrt(static.shape[1]),
            dtype=np.float64,
        )


class SubspaceScalingOverCovNode:
    """Applies spatial projection to covariance matrices using rank-one subspace directions.

    For each distance d the node computes  P[d] @ R[d] @ P[d],  where P[d] is
    a Hermitian matrix constructed from the rank-one subspace direction and the
    provided scalings.  Because P is Hermitian (P^H = P) the expression equals the
    standard covariance projection  P R P^H,  preserving positive semi-definiteness.
    """

    def __init__(
        self,
        num_points: int,
        num_channels: int,
    ) -> None:
        """
        :param num_points: Number of range points.
        :param num_channels: Number of spatial channels.
        """
        self.num_points = num_points
        self.num_channels = num_channels

    def execute(
        self,
        covariance_matrices: npt.NDArray[np.complex128],
        rank_one_subspaces: npt.NDArray[np.complex128],
        subspace_scaling: npt.NDArray[np.float64],
        orthogonal_scaling: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.complex128]:
        """
        :param covariance_matrices: Spatial covariance matrices,
            shape (num_points, num_channels, num_channels).
        :param rank_one_subspaces: Rank-one subspace direction per distance (need not be normalized),
            shape (num_points, num_channels).
        :param subspace_scaling: Scaling applied along the subspace direction,
            shape (num_points,).
        :param orthogonal_scaling: Scaling applied along orthogonal directions,
            shape (num_points,).
        :returns: Projected covariance matrices P @ R @ P, shape (num_points, num_channels, num_channels).
        """
        if covariance_matrices.shape != (self.num_points, self.num_channels, self.num_channels):
            msg = f"covariance_matrices: expected shape {(self.num_points, self.num_channels, self.num_channels)}, got {covariance_matrices.shape}"
            raise ValueError(msg)
        if rank_one_subspaces.shape != (self.num_points, self.num_channels):
            msg = f"rank_one_subspaces: expected shape {(self.num_points, self.num_channels)}, got {rank_one_subspaces.shape}"
            raise ValueError(msg)
        if subspace_scaling.shape != (self.num_points,):
            msg = f"subspace_scaling: expected shape {(self.num_points,)}, got {subspace_scaling.shape}"
            raise ValueError(msg)
        if orthogonal_scaling.shape != (self.num_points,):
            msg = f"orthogonal_scaling: expected shape {(self.num_points,)}, got {orthogonal_scaling.shape}"
            raise ValueError(msg)

        projection_matrices = _build_projection_matrices(
            rank_one_subspaces, subspace_scaling, orthogonal_scaling, self.num_channels
        )

        # P is Hermitian (P^H = P), so  P R P^H = P R P
        return projection_matrices @ covariance_matrices @ projection_matrices


class SubspaceScalingOverSweepsNode:
    """Applies spatial projection directly to sweep data via Hermitian projection.

    For each distance d the node computes  P[d] @ x  for every sweep vector x at that distance,
    where P[d] is a Hermitian matrix constructed from the rank-one subspace direction and the
    provided scalings. Averaging the outer products of the projected sweeps is equivalent to
    P R P^H = P R P.
    """

    def __init__(
        self,
        num_points: int,
        num_sweeps: int,
        num_channels: int,
    ) -> None:
        """
        :param num_points: Number of range points.
        :param num_sweeps: Number of sweeps per frame.
        :param num_channels: Number of spatial channels.
        """
        self.num_points = num_points
        self.num_sweeps = num_sweeps
        self.num_channels = num_channels

    def execute(
        self,
        sweeps: npt.NDArray[np.complex128],
        rank_one_subspaces: npt.NDArray[np.complex128],
        subspace_scaling: npt.NDArray[np.float64],
        orthogonal_scaling: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.complex128]:
        """
        :param sweeps: Sweep data, shape (num_sweeps, num_points, num_channels).
        :param rank_one_subspaces: Rank-one subspace direction per distance (need not be normalized),
            shape (num_points, num_channels).
        :param subspace_scaling: Scaling applied along the subspace direction,
            shape (num_points,).
        :param orthogonal_scaling: Scaling applied along orthogonal directions,
            shape (num_points,).
        :returns: Projected sweep data P[d] @ x for each sweep x at distance d,
            shape (num_sweeps, num_points, num_channels).
        """
        if sweeps.shape != (self.num_sweeps, self.num_points, self.num_channels):
            msg = f"sweeps: expected shape {(self.num_sweeps, self.num_points, self.num_channels)}, got {sweeps.shape}"
            raise ValueError(msg)
        if rank_one_subspaces.shape != (self.num_points, self.num_channels):
            msg = f"rank_one_subspaces: expected shape {(self.num_points, self.num_channels)}, got {rank_one_subspaces.shape}"
            raise ValueError(msg)
        if subspace_scaling.shape != (self.num_points,):
            msg = f"subspace_scaling: expected shape {(self.num_points,)}, got {subspace_scaling.shape}"
            raise ValueError(msg)
        if orthogonal_scaling.shape != (self.num_points,):
            msg = f"orthogonal_scaling: expected shape {(self.num_points,)}, got {orthogonal_scaling.shape}"
            raise ValueError(msg)

        projection_matrices = _build_projection_matrices(
            rank_one_subspaces, subspace_scaling, orthogonal_scaling, self.num_channels
        )

        # result[s,d,i] = sum_j P[d,i,j] * sweeps[s,d,j]  i.e. P[d] @ x for each sweep x at d
        result = np.einsum("dij,sdj->sdi", projection_matrices, sweeps)
        return np.asarray(result, dtype=np.complex128)
