# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import numpy as np
import numpy.typing as npt

import acconeer.exptool.a2.algo._utils as utils


T = t.TypeVar("T", bound=t.Union[np.floating[t.Any], np.complexfloating[t.Any, t.Any]])


class ExponentialLowPassNode(t.Generic[T]):
    """Exponential lowpass filter (first-order IIR). lp_constant in [0, 1): 0 = instant
    tracking, values near 1 = heavy smoothing.

    warmup=True (default): ramps the effective time constant from zero over the first calls,
    avoiding the initial transient. warmup=False: uses lp_constant directly from the first call.

    init_value: initial filter state. Defaults to zeros when None."""

    def __init__(
        self,
        input_shape: t.Tuple[int, ...],
        lp_constant: np.float64,
        dtype: type[T],
        warmup: bool = True,
        init_value: t.Optional[npt.NDArray[T]] = None,
    ) -> None:
        if not 0.0 <= float(lp_constant) < 1.0:
            msg = f"lp_constant must be in [0.0, 1.0), got {float(lp_constant)}"
            raise ValueError(msg)
        if warmup and init_value is not None:
            msg = (
                "init_value cannot be set when warmup is True; the warmup ramp "
                "overrides the initial state on the first call."
            )
            raise ValueError(msg)
        if init_value is not None and init_value.shape != input_shape:
            msg = f"init_value.shape {init_value.shape} does not match input_shape {input_shape}"
            raise ValueError(msg)
        self.lp_constant = lp_constant
        self._warmup = warmup
        self.filt: npt.NDArray[T] = (
            np.zeros(input_shape, dtype=dtype) if init_value is None else init_value.copy()
        )
        self._num_updates = 0

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        if self._warmup:
            lp_constant = utils.warmup_filter_const(float(self.lp_constant), self._num_updates)
        else:
            lp_constant = float(self.lp_constant)
        self.filt = t.cast(
            npt.NDArray[T],
            self.filt * lp_constant + inp * (1.0 - lp_constant),
        )
        self._num_updates += 1
        return self.filt


class DelayedExponentialHighPassNode(t.Generic[T]):
    """High pass filter node using a delayed (z^-1) ExponentialLowPassNode: Returns input
    minus the previous background estimate, then updates — the background is one sample delayed
    relative to the input. At lp_constant=0 this reduces to a standard 1-pulse MTI:
    output = x[n] - x[n-1].

    Without init_value the first call has no background to subtract and returns zeros,
    so the static part of the first input does not pass through.

    warmup and init_value are forwarded to the internal ExponentialLowPassNode."""

    def __init__(
        self,
        input_shape: t.Tuple[int, ...],
        lp_constant: np.float64,
        dtype: type[T],
        warmup: bool = True,
        init_value: t.Optional[npt.NDArray[T]] = None,
    ) -> None:
        self.filt_node: ExponentialLowPassNode[T] = ExponentialLowPassNode(
            input_shape=input_shape,
            lp_constant=lp_constant,
            dtype=dtype,
            warmup=warmup,
            init_value=init_value,
        )
        self._has_background = init_value is not None

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        if self._has_background:
            movement = t.cast(npt.NDArray[T], inp - self.filt_node.filt)
        else:
            movement = np.zeros_like(inp)
            self._has_background = True
        self.filt_node.execute(inp)
        return movement


class ExponentialHighPassNode(t.Generic[T]):
    """High pass filter node using ExponentialLowPassNode: Updates the
    background first, then returns input minus the current estimate. Unlike
    DelayedExponentialHighPassNode the current sample is absorbed into the background before
    subtraction.
    Note: lp_constant=0 makes the background track the input exactly, yielding zero output.

    warmup and init_value are forwarded to the internal ExponentialLowPassNode."""

    def __init__(
        self,
        input_shape: t.Tuple[int, ...],
        lp_constant: np.float64,
        dtype: type[T],
        warmup: bool = True,
        init_value: t.Optional[npt.NDArray[T]] = None,
    ) -> None:
        self.filt_node: ExponentialLowPassNode[T] = ExponentialLowPassNode(
            input_shape=input_shape,
            lp_constant=lp_constant,
            dtype=dtype,
            warmup=warmup,
            init_value=init_value,
        )

    def execute(self, inp: npt.NDArray[T]) -> npt.NDArray[T]:
        self.filt_node.execute(inp)
        movement = t.cast(npt.NDArray[T], inp - self.filt_node.filt)
        return movement
