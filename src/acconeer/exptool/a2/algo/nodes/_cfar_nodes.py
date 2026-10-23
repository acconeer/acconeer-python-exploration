# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""1D and 2D CFAR threshold-map convenience wrappers.

The wrappers in this module are example compositions of the sub-nodes in
:mod:`._cfar_subnodes` (integral image, arm extraction, aggregate, scaling,
sidelobe compensation). All aggregation is expressed via
:class:`CFARAggregateMethod` from :mod:`._cfar_subnodes`; the 2D wrapper takes a
per-axis tuple so each axis can pick its own method (or ``None`` to skip
that axis entirely).
"""

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt

from acconeer.exptool.a2.algo.nodes._cfar_subnodes import (
    ArmExtraction1DNode,
    ArmExtraction2DNode,
    AxisPoolNode,
    CFARAggregateMethod,
    CFARAggregateNode,
    CFARKernelType,
    CFARScalingNode,
    IntegralImageNode,
    SidelobeCompensationNode,
)


_NDf64 = npt.NDArray[np.float64]


class CFAR1DThresholdNode:
    """1D Constant False Alarm Rate (CFAR) threshold map node using integral
    images for O(N) performance.

    Computes a per-cell detection threshold by averaging the power in a sliding
    reference window. The window is split into two **arms** — one on each side of a
    guard band — and ``aggregate_method`` controls how those arms are combined into
    the noise estimate. The threshold scales with the local noise estimate so that the
    false-positive rate stays approximately constant across varying noise floors.

    Window layout around each Cell Under Test (CUT)::

        R = Reference  |  G = Guard  |  C = CUT
             LEFT ARM                                                 RIGHT ARM
        <-- ref_radius --><- guard_radius ->    <- guard_radius -><-- ref_radius -->
        | R R R R R R R R | G G G G G G G G | C | G G G G G G G G | R R R R R R R R |

    **Boundary behavior**: near the edges the reference window is clipped to the
    available data, so fewer cells contribute to the noise estimate.  The threshold
    scaling factor ``N * (FPR^(−1/N) − 1)`` is evaluated with the actual cell count
    ``N``, which keeps the false-positive rate constant regardless of how many cells
    are available.
    """

    def __init__(
        self,
        input_shape: t.Tuple[int],
        guard_radius: int,
        ref_radius: int,
        aggregate_method: CFARAggregateMethod = CFARAggregateMethod.CA,
        theoretical_fpr: float = 1e-2,
        fixed_threshold: float = 0.0,
        side_lobe_compensation_dB: t.Optional[float] = None,
    ):
        """
        :param input_shape: Shape of the 1D array passed to :meth:`execute`, as a length-1
            tuple. ``execute`` validates the input shape against this value.
        :param guard_radius: Width of the guard band (cells excluded from the reference window).
        :param ref_radius: Width of the reference window on each side of the guard band.
        :param aggregate_method: How to combine the left and right reference arms into
            the noise estimate. See :class:`CFARAggregateMethod`.
        :param theoretical_fpr: Target false positive rate assuming independent,
            exponentially distributed noise cells. Target signal leakage and correlated samples
            shift the observed FPR away from this value. Tune empirically to hit the desired
            operating point.
        :param fixed_threshold: Hard minimum threshold; the computed threshold is clipped to
            at least this value.
        :param side_lobe_compensation_dB: If set, raises the threshold to at least this many dB
            below the global maximum, suppressing sidelobes. Must be smaller than zero.
        """
        self._input_shape = tuple(input_shape)
        if len(self._input_shape) != 1:
            msg = f"CFAR1DThresholdNode requires a 1D input_shape, got {self._input_shape}."
            raise ValueError(msg)
        self._integral = IntegralImageNode()
        self._II_ones = self._integral.execute(np.ones(self._input_shape, dtype=np.float64))
        self._arm_extract = ArmExtraction1DNode(guard_radius=guard_radius, ref_radius=ref_radius)
        self._aggregate = CFARAggregateNode(method=aggregate_method)
        self._scaling = CFARScalingNode(
            theoretical_fpr=theoretical_fpr, fixed_threshold=fixed_threshold
        )
        self._sidelobe = SidelobeCompensationNode(side_lobe_compensation_dB, axis=0)

    def execute(self, map_1d: _NDf64) -> _NDf64:
        """Compute a 1D CFAR threshold map.

        :param map_1d: 1D power/amplitude array of shape ``input_shape``.
        :returns: 1D threshold map of the same shape.
        """
        if map_1d.shape != self._input_shape:
            msg = (
                f"CFAR1DThresholdNode expected input of shape {self._input_shape}, "
                f"got {map_1d.shape}."
            )
            raise ValueError(msg)

        II_data = self._integral.execute(map_1d)
        arms = self._arm_extract.execute(II_data, self._II_ones)
        arm_sum, num_samples = self._aggregate.execute(arms)
        threshold = self._scaling.execute(arm_sum, num_samples)
        return self._sidelobe.execute(threshold, map_1d)


class CFAR2DThresholdNode:
    """2D Constant False Alarm Rate (CFAR) threshold map node using 2D integral
    images for O(N·M) performance.

    Extends 1D CFAR to two dimensions using a thin or thick cross kernel.
    The reference window is divided into four **arms**: *left* and *right* along
    axis 0, and *near* and *far* along axis 1. ``aggregate_method`` controls how
    the reference cells in arms are combined per axis into the noise estimate.

    THIN_CROSS kernel layout around each Cell Under Test (CUT)::
        R = Reference  |  G = Guard  |  C = CUT
                                                   _  ^
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  | ref_radii[1]     NEAR ARM
                                                   R  |
                                                   R  |
                                                   R  |
                                                   _  v
                                                   _  ^
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  | guard_radii[1]
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  |
               LEFT ARM                            _  v                              RIGHT ARM
        <--- ref_radii[0] ---><-- guard_radii[0] --->   <-- guard_radii[0] ---><--- ref_radii[0] --->
        | R R R R R R R R R R | G G G G G G G G G G | C | G G G G G G G G G G | R R R R R R R R R R |
                                                   _  ^
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  | guard_radii[1]
                                                   G  |
                                                   G  |
                                                   G  |
                                                   G  |
                                                   _  v
                                                   _  ^
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  |
                                                   R  | ref_radii[1]     FAR ARM
                                                   R  |
                                                   R  |
                                                   R  |
                                                   _  v

    THICK_CROSS will have an arm width equal to the opposite dimensions (G + C cells).

    **Boundary behavior**: near the edges the reference window is clipped to the
    available data, so fewer cells contribute to the noise estimate.  The threshold
    scaling factor ``N * (FPR^(−1/N) − 1)`` is evaluated with the actual cell count
    ``N``, which keeps the false-positive rate constant regardless of how many cells
    are available.
    """

    def __init__(
        self,
        input_shape: t.Tuple[int, int],
        guard_radii: t.Tuple[int, int],
        ref_radii: t.Tuple[int, int],
        kernel_type: CFARKernelType = CFARKernelType.THIN_CROSS,
        aggregate_method: t.Tuple[CFARAggregateMethod, CFARAggregateMethod] = (
            CFARAggregateMethod.CA,
            CFARAggregateMethod.CA,
        ),
        theoretical_fpr: float = 1e-2,
        fixed_threshold: float = 0.0,
        side_lobe_compensation_dB: t.Tuple[t.Optional[float], t.Optional[float]] = (None, None),
    ):
        """
        :param input_shape: Shape ``(N0, N1)`` of the 2D array passed to :meth:`execute`.
            ``execute`` validates the input shape against this value.
        :param guard_radii: Guard Widths ``(axis0, axis1)`` in cells.
        :param ref_radii: Reference window Widths ``(axis0, axis1)`` in cells.
        :param kernel_type: Shape of the reference window (``THIN_CROSS`` or ``THICK_CROSS``).
        :param aggregate_method: Per-axis aggregation ``(axis0, axis1)``. Each entry is an
            :class:`CFARAggregateMethod`; use ``CFARAggregateMethod.DROP`` to skip that axis. At least
            one entry must be non-``DROP``.
        :param theoretical_fpr: Target false positive rate assuming independent,
            exponentially distributed noise cells. Target signal leakage and correlated samples
            shift the observed FPR away from this value. Tune empirically to hit the desired
            operating point.
        :param fixed_threshold: Hard minimum threshold applied after CFAR scaling.
        :param side_lobe_compensation_dB: Per-axis sidelobe floor ``(axis0_dB, axis1_dB)``;
            raises the threshold to at least this many dB below the per-axis maximum. Each
            element is independently optional (``None`` disables the floor on that axis).
            Non-``None`` values must be smaller than zero.
        """
        axis0_method, axis1_method = aggregate_method
        if axis0_method == CFARAggregateMethod.DROP and axis1_method == CFARAggregateMethod.DROP:
            msg = "aggregate_method must have at least one non-DROP entry."
            raise ValueError(msg)

        self._input_shape = tuple(input_shape)
        if len(self._input_shape) != 2:
            msg = f"CFAR2DThresholdNode requires a 2D input_shape, got {self._input_shape}."
            raise ValueError(msg)
        self._integral = IntegralImageNode()
        self._II_ones = self._integral.execute(np.ones(self._input_shape, dtype=np.float64))
        self._arm_extract = ArmExtraction2DNode(
            guard_radii=guard_radii, ref_radii=ref_radii, kernel_type=kernel_type
        )
        self._axis0_aggregate = CFARAggregateNode(method=axis0_method, axis=0)
        self._axis1_aggregate = CFARAggregateNode(method=axis1_method, axis=1)
        self._axis_pool = AxisPoolNode()
        self._scaling = CFARScalingNode(
            theoretical_fpr=theoretical_fpr, fixed_threshold=fixed_threshold
        )
        dB_axis0, dB_axis1 = side_lobe_compensation_dB
        self._sidelobe_axis0 = SidelobeCompensationNode(dB_axis0, axis=0)
        self._sidelobe_axis1 = SidelobeCompensationNode(dB_axis1, axis=1)

    def execute(self, map_2d: _NDf64) -> _NDf64:
        """Compute a 2D CFAR threshold map.

        :param map_2d: 2D power/amplitude array of shape ``input_shape``.
        :returns: 2D threshold map of the same shape.
        """
        if map_2d.shape != self._input_shape:
            msg = (
                f"CFAR2DThresholdNode expected input of shape {self._input_shape}, "
                f"got {map_2d.shape}."
            )
            raise ValueError(msg)

        II_data = self._integral.execute(map_2d)
        arms = self._arm_extract.execute(II_data, self._II_ones)

        total_s, total_c = self._axis_pool.execute(
            self._axis0_aggregate.execute(arms),
            self._axis1_aggregate.execute(arms),
        )

        threshold = self._scaling.execute(total_s, total_c)
        threshold = self._sidelobe_axis0.execute(threshold, map_2d)
        return self._sidelobe_axis1.execute(threshold, map_2d)
