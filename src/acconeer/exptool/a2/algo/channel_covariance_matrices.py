# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import functools
import typing as t

import attrs
import numpy as np
import numpy.typing as npt
import scipy
import typing_extensions as te

from acconeer.exptool._core.class_creation.attrs import attrs_ndarray_validator
from acconeer.exptool.a2._core import channel_convention as ch_conv


def batched_cholesky_solver(
    A_batch: npt.NDArray[np.complex128], B_batch: npt.NDArray[np.complex128]
) -> npt.NDArray[np.complex128]:
    """
    Typically slower than np.linalg.inv on our matrix sizes.
    However, matches the implementation in C.
    """
    results = []
    for A, B in zip(A_batch, B_batch):
        c, lower = scipy.linalg.cho_factor(A)
        x = scipy.linalg.cho_solve((c, lower), B)
        results.append(x)
    return np.array(results)


def get_matrices_inverses(
    array_3d: npt.NDArray[np.complex128], ids: npt.NDArray[np.complex128]
) -> npt.NDArray[np.complex128]:
    if array_3d.ndim != 3:
        msg = "Array needs to have 3 dimensions"
        raise ValueError(msg)
    try:
        return batched_cholesky_solver(array_3d, ids)
    except np.linalg.LinAlgError:
        return np.full(array_3d.shape, np.nan, dtype=np.complex128)


def get_matrices_eigendecomposition(
    array_3d: npt.NDArray[np.complex128],
) -> te.Tuple[npt.NDArray[np.float64], npt.NDArray[np.complex128]]:
    if array_3d.ndim != 3:
        msg = "Array needs to have 3 dimensions"
        raise ValueError(msg)
    try:
        return np.linalg.eigh(
            array_3d
        )  # matrix is hermitian, so we can do a faster eigenvalue calculation (compared to eig)
    except np.linalg.LinAlgError:
        return (
            np.full(array_3d.shape[:-1], np.nan, dtype=np.float64),
            np.full(array_3d.shape, np.nan, dtype=np.complex128),
        )


@attrs.frozen(slots=False)
class ChannelCovarianceMatrices:
    """A collection of channel covariance matrices.

    Estimates the covariance between multiple channels corresponding to a single depth
    """

    matrices: npt.NDArray[np.complex128] = attrs.field(
        validator=attrs_ndarray_validator(ndim=3, element_type=np.complex128)
    )
    """The matrices themselves. All matrices are stacked along the first axis"""

    tx_mask: int
    """rx mask of input data"""

    rx_mask: int
    """tx mask of input data"""

    beta: float
    """Exponential smoothing factor between updates"""

    num_updates: int
    """How many times the matrices have been updated"""

    @functools.cached_property
    def inverse_matrices(self) -> npt.NDArray[np.complex128]:
        """The inverse of each matrix in ``matrices``. Lazily computed for performance"""
        return get_matrices_inverses(self.matrices, self.ids)

    def eigendecomposition(self) -> te.Tuple[npt.NDArray[np.float64], npt.NDArray[np.complex128]]:
        return get_matrices_eigendecomposition(self.matrices)

    @functools.cached_property
    def ids(self) -> npt.NDArray[np.complex128]:
        """Identity matrices of the right size, used since we are using a solver instead of an inverter."""
        return np.stack([np.eye(self.matrices.shape[1])] * self.matrices.shape[0])

    @classmethod
    def initial(cls, tx_mask: int, rx_mask: int, num_distances: int, beta: float) -> te.Self:
        """Creates an initial collection of covariance matrices

        >>> initial = ChannelCovarianceMatrices.initial(tx_mask=0b001, rx_mask=0b0011, num_distances=2, beta=0.9)
        >>> initial.matrices
        array([[[1.+0.j, 0.+0.j],
                [0.+0.j, 1.+0.j]],
               [[1.+0.j, 0.+0.j],
                [0.+0.j, 1.+0.j]]])
        >>> initial.beta
        0.9
        >>> initial.num_updates
        0
        >>> initial.inverse_matrices
        array([[[1.+0.j, 0.+0.j],
                [0.+0.j, 1.+0.j]],
               [[1.+0.j, 0.+0.j],
                [0.+0.j, 1.+0.j]]])
        """
        tx_antenna_count = bin(tx_mask).count("1")
        rx_antenna_count = bin(rx_mask).count("1")
        num_channels = tx_antenna_count * rx_antenna_count

        single_matrix = np.eye(num_channels, dtype=np.complex128)
        initial_matrices = np.broadcast_to(
            single_matrix, shape=(num_distances, *single_matrix.shape)
        )
        return cls(
            matrices=initial_matrices,
            tx_mask=tx_mask,
            rx_mask=rx_mask,
            beta=beta,
            num_updates=0,
        )

    @property
    def _used_beta(self) -> float:
        """The first few updates will 'smooth' faster"""
        return min(self.beta, self.num_updates / (self.num_updates + 1))

    def submatrices(
        self, tx_mask: int, rx_mask: int, depths: t.Optional[list[int]] = None
    ) -> npt.NDArray[np.complex128]:
        """
        Returns a subset of the covariance matrices according to the supplied masks and depths.
        The masks are in the standard format and the depths in so called "fancy indexing".

        Examples:

        >>> ChannelCovarianceMatrices.initial(tx_mask=0b111,
        ...                                   rx_mask=0b0001,
        ...                                   num_distances=1,
        ...                                   beta=0.9).submatrices(1, 1)
        array([[[1.+0.j]]])
        >>> import numpy as np
        >>>
        >>> init = np.array(
        ...    [[[1, 2, 3],
        ...      [4, 5, 6],
        ...      [7, 8, 9]]]
        ... ).astype(np.complex128)
        >>>
        >>> ChannelCovarianceMatrices(
        ...     init,
        ...     tx_mask=0b001,
        ...     rx_mask=0b0111,
        ...     beta=0.9,
        ...     num_updates=0,
        ... ).submatrices(0b1, 0b10)
        array([[[5.+0.j]]])
        >>> matrices = ChannelCovarianceMatrices(
        ...     init,
        ...     tx_mask=0b001,
        ...     rx_mask=0b0111,
        ...     beta=0.9,
        ...     num_updates=0,
        ... ).submatrices(0b11, 0b1011)
        Traceback (most recent call last):
        ...
        ValueError: Covariance matrices only has data for channels
        defined by masks tx=0b1,rx=0b111 but tried to get tx=0b11,rx=0b1011

        """
        if (tx_mask & self.tx_mask) != tx_mask or (rx_mask & self.rx_mask) != rx_mask:
            msg = (
                f"Covariance matrices only has data for channels defined by masks tx={bin(self.tx_mask)},"
                + f"rx={bin(self.rx_mask)} but tried to get tx={bin(tx_mask)},rx={bin(rx_mask)}"
            )
            raise ValueError(msg)

        # check default case
        if tx_mask == self.tx_mask and rx_mask == self.rx_mask and depths is None:
            return self.matrices
        channels = ch_conv.get_subset_channel_indexes(self.tx_mask, self.rx_mask, tx_mask, rx_mask)
        if depths is not None:
            a = np.take(self.matrices, depths, axis=0)
        else:
            a = self.matrices
        b = np.take(a, channels, axis=1)
        c = np.take(b, channels, axis=2)
        return c

    def updated(self, channel_data: npt.NDArray[np.complex128]) -> te.Self:
        """Calculate and return the update of this ``ChannelCovarianceMatrices``

        ``channel_data`` is all the data points for all channels of a measured point.

        Trying to update the matrices with misshapen data will raise a ValueError:

        >>> matrices = ChannelCovarianceMatrices.initial(tx_mask=0b001, rx_mask=0b0011, num_distances=1, beta=0.5)
        >>> matrices.updated(np.array([[0+0j, 0+0j, 0+0j]]))
        Traceback (most recent call last):
        ...
        ValueError: 'channel_data' is misshapen. Expected shape (1, 2) but got (1, 3)

        >>> matrices.updated(np.array([[1+1j, 1+0j]])).matrices[0]
        array([[2.+0.j, 1.+1.j],
               [1.-1.j, 1.+0.j]])

        If the matrices are updated with data points with a fixed offset between the channels,
        the covariance will be higher

        >>> np.set_printoptions(precision=2, suppress=True)
        >>>
        >>> high_covariance_matrices = matrices
        >>> for _ in range(50):
        ...     point = 1 + 0j
        ...     offset = np.exp(1j * np.pi / 8)  # the imaginary object is slightly off center.
        ...
        ...     data = np.array([[point, point * offset]])
        ...     high_covariance_matrices = high_covariance_matrices.updated(data)
        ...
        >>> high_covariance_matrices.matrices
        array([[[...       , 0.92-0.38j],
                [0.92+0.38j, ...       ]]])

        If the matrix is updated with data points of random phase offset, the covariance will
        be lower:

        >>> import random
        >>> random.seed(0)
        >>>
        >>> low_covariance_matrices = matrices
        >>> for _ in range(50):
        ...     point = 1 + 0j
        ...     offset = np.exp(2j * np.pi * random.random())
        ...
        ...     data = np.array([[point, point * offset]])
        ...     low_covariance_matrices = low_covariance_matrices.updated(data)
        ...
        >>> low_covariance_matrices.matrices
        array([[[...       , 0.43-0.15j],
                [0.43+0.15j, ...       ]]])
        """
        if (actual_shape := channel_data.shape) != (expected_shape := self.matrices.shape[:-1]):
            msg = f"'channel_data' is misshapen. Expected shape {expected_shape} but got {actual_shape}"
            raise ValueError(msg)

        outers = np.array([np.outer(depth_data, depth_data.conj()) for depth_data in channel_data])
        return attrs.evolve(
            self,
            matrices=self.matrices * self._used_beta + (1 - self._used_beta) * outers,
            num_updates=self.num_updates + 1,
        )
