# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Unit tests for the nodes in ``_simple_nodes`` that carry non-trivial logic.

The thin ``numpy`` wrappers (``NoopNode``, ``MeanNode``, ``MaxNode``,
``ReshapeNode``) are exercised via the processor golden tests. This file
pins behaviours specific to:

* ``ArgmaxNode`` — axis handling, scalar-vs-array return.
* ``IndexedSliceStackNode`` — gather along a configurable axis, including
  the non-trailing-axis and empty-indices cases.
* ``CovarianceSubarrayNode`` — channel-index gathering on a square cov
  matrix.
* ``ZeroHoldoffNode`` — zeros for the first calls, pass-through after.
"""

from __future__ import annotations

import numpy as np
import pytest

from acconeer.exptool.a2.algo.nodes._simple_nodes import (
    ArgmaxNode,
    CovarianceSubarrayNode,
    IndexedSliceStackNode,
    ZeroHoldoffNode,
)


# --- ArgmaxNode ---


class TestArgmaxNode:
    def test_axis_none_returns_scalar_index(self) -> None:
        data = np.array([[1.0, 5.0], [2.0, 3.0]])
        out = ArgmaxNode(axis=None).execute(data)
        # Flat index of the 5.0 cell.
        assert int(out) == 1

    def test_axis_minus_one(self) -> None:
        data = np.array([[1.0, 5.0, 2.0], [4.0, 0.0, 3.0]])
        out = ArgmaxNode(axis=-1).execute(data)
        assert np.array_equal(out, np.array([1, 0]))

    def test_empty_rows_returns_empty(self) -> None:
        data = np.empty((0, 5))
        out = ArgmaxNode(axis=1).execute(data)
        assert out.shape == (0,)


# --- IndexedSliceStackNode ---


class TestIndexedSliceStackNode:
    def test_trailing_axis_gather(self) -> None:
        # (D, AZ, EL) = (2, 3, 4). slice_axis=2 -> gather (EL,) slices at (d, az).
        data = np.arange(2 * 3 * 4, dtype=float).reshape(2, 3, 4)
        out = IndexedSliceStackNode(slice_axis=2).execute(data, [(0, 0), (1, 2)])
        assert out.shape == (2, 4)
        np.testing.assert_array_equal(out[0], data[0, 0, :])
        np.testing.assert_array_equal(out[1], data[1, 2, :])

    def test_negative_slice_axis(self) -> None:
        data = np.arange(2 * 3 * 4, dtype=float).reshape(2, 3, 4)
        out = IndexedSliceStackNode(slice_axis=-1).execute(data, [(0, 1)])
        np.testing.assert_array_equal(out[0], data[0, 1, :])

    def test_non_trailing_slice_axis(self) -> None:
        # Slice along axis 1 of shape (3, 4, 5). After moveaxis, the slices
        # are (4,) long and the indexers address (axis0, axis2).
        data = np.arange(3 * 4 * 5, dtype=float).reshape(3, 4, 5)
        out = IndexedSliceStackNode(slice_axis=1).execute(data, [(0, 2), (1, 4)])
        assert out.shape == (2, 4)
        np.testing.assert_array_equal(out[0], data[0, :, 2])
        np.testing.assert_array_equal(out[1], data[1, :, 4])

    def test_empty_indices_returns_empty_stack(self) -> None:
        data = np.arange(2 * 3 * 4, dtype=float).reshape(2, 3, 4)
        out = IndexedSliceStackNode(slice_axis=2).execute(data, [])
        assert out.shape == (0, 4)

    def test_dtype_preserved(self) -> None:
        data = np.arange(8, dtype=np.complex128).reshape(2, 4)
        out = IndexedSliceStackNode(slice_axis=1).execute(data, [(0,), (1,)])
        assert out.dtype == np.complex128
        np.testing.assert_array_equal(out[0], data[0, :])
        np.testing.assert_array_equal(out[1], data[1, :])


@pytest.mark.parametrize(
    ("shape", "slice_axis", "indices"),
    [
        ((2, 3, 4), 0, [(0, 0), (1, 2), (2, 3)]),  # slice over axis 0 length 2
        ((5,), 0, [()]),  # 1D: single empty tuple -> full slice
    ],
)
def test_indexed_slice_stack_shapes(shape: tuple, slice_axis: int, indices: list) -> None:
    data = np.arange(int(np.prod(shape)), dtype=float).reshape(shape)
    out = IndexedSliceStackNode(slice_axis=slice_axis).execute(data, indices)
    expected_k = shape[slice_axis]
    assert out.shape == (len(indices), expected_k)


# --- CovarianceSubarrayNode ---


class TestCovarianceSubarrayNode:
    @staticmethod
    def _random_hermitian_batch(batch: int, channels: int, seed: int = 0) -> np.ndarray:
        rng = np.random.default_rng(seed)
        a = rng.standard_normal((batch, channels, channels)) + 1j * rng.standard_normal(
            (batch, channels, channels)
        )
        return a @ np.swapaxes(a.conj(), -1, -2)

    def test_shape_on_batched_input(self) -> None:
        cov = self._random_hermitian_batch(batch=4, channels=12, seed=1)
        out = CovarianceSubarrayNode([0, 4, 8]).execute(cov)
        assert out.shape == (4, 3, 3)

    def test_values_match_manual_selection_list_indices(self) -> None:
        cov = self._random_hermitian_batch(batch=2, channels=6, seed=2)
        indices = [0, 2, 5]
        out = CovarianceSubarrayNode(indices).execute(cov)
        expected = cov[:, indices][:, :, indices]
        np.testing.assert_array_equal(out, expected)

    def test_values_match_manual_selection_ndarray_indices(self) -> None:
        cov = self._random_hermitian_batch(batch=3, channels=8, seed=3)
        indices = np.array([1, 3, 4, 7], dtype=np.intp)
        out = CovarianceSubarrayNode(indices).execute(cov)
        expected = cov[:, indices][:, :, indices]
        np.testing.assert_array_equal(out, expected)

    def test_preserves_hermitian_structure(self) -> None:
        cov = self._random_hermitian_batch(batch=2, channels=6, seed=4)
        out = CovarianceSubarrayNode([0, 1, 5]).execute(cov)
        np.testing.assert_allclose(out, np.swapaxes(out.conj(), -1, -2))

    def test_unbatched_square_input(self) -> None:
        cov = self._random_hermitian_batch(batch=1, channels=5, seed=5)[0]
        out = CovarianceSubarrayNode([1, 3]).execute(cov)
        assert out.shape == (2, 2)
        np.testing.assert_array_equal(out, cov[np.ix_([1, 3], [1, 3])])

    def test_rejects_empty_indices(self) -> None:
        with pytest.raises(ValueError):
            CovarianceSubarrayNode([])

    def test_rejects_non_square_input(self) -> None:
        cov = np.zeros((2, 3, 4), dtype=np.complex128)
        with pytest.raises(ValueError):
            CovarianceSubarrayNode([0, 1]).execute(cov)


# --- ZeroHoldoffNode ---


class TestZeroHoldoffNode:
    def test_zeros_during_holdoff_then_passes_through(self) -> None:
        node: ZeroHoldoffNode[np.float64] = ZeroHoldoffNode(
            input_shape=(2, 2), dtype=np.float64, num_holdoff_calls=2
        )
        inp = np.array([[1.0, 2.0], [3.0, 4.0]])
        for _ in range(2):
            out = node.execute(inp)
            np.testing.assert_array_equal(out, np.zeros_like(inp))
            assert out.dtype == inp.dtype
        np.testing.assert_array_equal(node.execute(inp), inp)
        np.testing.assert_array_equal(node.execute(inp), inp)

    def test_zero_holdoff_passes_through_immediately(self) -> None:
        inp = np.array([1.0, -1.0])
        out = ZeroHoldoffNode(input_shape=(2,), dtype=np.float64, num_holdoff_calls=0).execute(inp)
        np.testing.assert_array_equal(out, inp)

    def test_rejects_negative_holdoff(self) -> None:
        with pytest.raises(ValueError):
            ZeroHoldoffNode(input_shape=(1,), dtype=np.float64, num_holdoff_calls=-1)
