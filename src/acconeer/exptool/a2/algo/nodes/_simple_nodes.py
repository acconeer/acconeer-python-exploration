# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar, cast

import numpy as np
import numpy.typing as npt


T = TypeVar("T", bound=np.number[Any])


class NoopNode(Generic[T]):
    """Passes input through. Compatible with any type."""

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        return inp


class MeanNode(Generic[T]):
    """Standard numpy mean wrapper."""

    def __init__(self, axis: int | tuple[int, ...] | None) -> None:
        self.axis = axis

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T] | T:
        # Perform calculation
        result = np.mean(cast(Any, inp), axis=self.axis)

        # If result is a scalar, extract it
        if np.isscalar(result):
            return cast(T, result)

        return cast(npt.NDArray[T], result)


class MaxNode(Generic[T]):
    """Standard numpy max wrapper."""

    def __init__(self, axis: int | tuple[int, ...] | None) -> None:
        self.axis = axis

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T] | T:
        result = np.max(cast(Any, inp), axis=self.axis)

        if np.isscalar(result):
            return cast(T, result)

        return cast(npt.NDArray[T], result)


class SubtractNode(Generic[T]):
    """Element-wise binary subtraction: ``minuend - subtrahend``."""

    def execute(
        self,
        minuend: npt.NDArray[T],
        subtrahend: npt.NDArray[T],
    ) -> npt.NDArray[T]:
        return cast(npt.NDArray[T], minuend - subtrahend)


class ConstantGainNode(Generic[T]):
    """Element-wise multiplication by a gain fixed at construction: ``inp * gain``."""

    def __init__(self, gain: float) -> None:
        self.gain = gain

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        return cast(npt.NDArray[T], inp * self.gain)


class ArgmaxNode(Generic[T]):
    """Standard numpy argmax wrapper."""

    def __init__(self, axis: int | None) -> None:
        self.axis = axis

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[np.intp] | np.intp:
        result = np.argmax(cast(Any, inp), axis=self.axis)

        if np.isscalar(result):
            return cast(np.intp, result)

        return cast(npt.NDArray[np.intp], result)


class IndexedSliceStackNode(Generic[T]):
    """Gathers 1D slices along ``slice_axis`` at a list of partial index tuples.

    Given an input array and a list of index tuples (one per output row),
    returns a stack of shape ``(N, K)`` where ``K`` is the length along
    ``slice_axis``. Each tuple addresses the non-sliced dimensions in their
    declaration order.

    Example: input shape ``(D, AZ, EL)`` with ``slice_axis=2`` and indices
    ``[(d0, az0), (d1, az1)]`` returns shape ``(2, EL)`` containing
    ``input[d0, az0, :]`` and ``input[d1, az1, :]``.
    """

    def __init__(self, slice_axis: int) -> None:
        self.slice_axis = slice_axis

    def execute(
        self,
        inp: npt.NDArray[T],
        indices: list[tuple[int, ...]],
    ) -> npt.NDArray[T]:
        slice_axis = self.slice_axis % inp.ndim
        moved = np.moveaxis(inp, slice_axis, -1)
        # moved has shape (non_sliced..., K). Index with the tuples into the
        # leading axes to gather (N, K).
        if not indices:
            return np.empty((0, moved.shape[-1]), dtype=inp.dtype)
        gathered = np.stack([moved[idx] for idx in indices], axis=0)
        return cast(npt.NDArray[T], gathered)


class ReshapeNode(Generic[T]):
    """Standard numpy reshape wrapper."""

    def __init__(self, target_shape: tuple[int, ...]) -> None:
        self.target_shape = target_shape

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        return np.reshape(inp, self.target_shape)


class CovarianceNode:
    """Computes the spatial covariance matrix (Hermitian)."""

    def __init__(self, axis: int) -> None:
        self.axis = axis

    def execute(self, data: npt.NDArray[T]) -> npt.NDArray[T]:
        data_swapped = np.swapaxes(data, self.axis, -1)
        # Using .conj() for the Hermitian product (standard for complex covariance)
        outers = np.einsum("...i,...j->...ij", data_swapped, data_swapped.conj())
        return np.moveaxis(outers, [-2, -1], [self.axis, self.axis + 1])


class CovarianceSubarrayNode(Generic[T]):
    """Extracts a sub-array covariance from a full channel covariance.

    Given a full per-batch covariance of shape ``(..., C, C)`` and a list
    of ``k`` channel indices into the ``C`` dimension, returns the
    sub-array covariance of shape ``(..., k, k)`` formed by selecting
    those rows and columns (in the given order).

    Useful for splitting a 12-channel array covariance into a 9- or
    6-channel sub-array covariance for beamforming with a sub-array
    steering vector set.
    """

    def __init__(self, indices: Sequence[int]) -> None:
        if len(indices) < 1:
            msg = "indices must contain at least one channel"
            raise ValueError(msg)
        self.indices = np.asarray(indices, dtype=np.intp)

    def execute(self, cov: npt.NDArray[T]) -> npt.NDArray[T]:
        if cov.ndim < 2 or cov.shape[-1] != cov.shape[-2]:
            msg = f"cov must have square trailing dims (..., C, C); got shape {cov.shape}"
            raise ValueError(msg)
        ix = self.indices
        return cast(npt.NDArray[T], cov[..., ix[:, None], ix[None, :]])


class ModeSelectNode:
    """
    Converts complex data to real-valued data based on mode.
    Note the return type change to float64.
    """

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def execute(self, data: npt.NDArray[np.complex128]) -> npt.NDArray[np.float64] | np.float64:
        if self.mode == "abs":
            ret = np.abs(data)
        elif self.mode == "angle":
            ret = np.angle(data)
        else:
            msg = f"Invalid mode '{self.mode}'"
            raise ValueError(msg)

        if isinstance(ret, np.ndarray):
            return ret.astype(np.float64)
        return np.float64(ret)


class NaNGuardNode(Generic[T]):
    """Guards downstream nodes against NaN propagation.

    If the input contains any ``NaN`` the entire array is replaced with
    ``fill_value`` (preserving shape and dtype). Otherwise the input is
    passed through unchanged.

    Use this instead of an inline ``if np.any(np.isnan(x))`` branch so the
    processor's ``execute`` sequence stays linear.
    """

    def __init__(self, fill_value: T) -> None:
        self.fill_value = fill_value

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        if np.any(np.isnan(inp)):
            return np.full_like(inp, self.fill_value)
        return inp


class ZeroHoldoffNode(Generic[T]):
    """Outputs zeros of ``input_shape`` for the first ``num_holdoff_calls``
    calls, then passes the input through unchanged.

    Use it to mute an estimate that is unreliable until enough samples have
    been averaged into it.
    """

    def __init__(
        self, input_shape: tuple[int, ...], dtype: type[T], num_holdoff_calls: int
    ) -> None:
        if num_holdoff_calls < 0:
            msg = f"num_holdoff_calls must be >= 0, got {num_holdoff_calls}"
            raise ValueError(msg)
        self.num_holdoff_calls = num_holdoff_calls
        self._zeros: npt.NDArray[T] = np.zeros(input_shape, dtype=dtype)
        self._num_calls = 0

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        held_off = self._num_calls < self.num_holdoff_calls
        self._num_calls += 1
        if held_off:
            return self._zeros
        return inp
