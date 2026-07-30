# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from collections import deque

import attrs


@attrs.mutable
class _InterruptCounter:
    """Counts presses that fall within a sliding time window.

    Each press reports how many presses the window currently holds:

    >>> counter = _InterruptCounter(window_s=5.0)
    >>> counter.press(now=0.0)
    1
    >>> counter.press(now=1.0)
    2
    >>> counter.press(now=2.0)
    3

    Presses that have fallen out of the window are forgotten, so a slow
    sequence never accumulates:

    >>> slow = _InterruptCounter(window_s=5.0)
    >>> slow.press(now=0.0)
    1
    >>> slow.press(now=6.0)
    1

    The window slides with the latest press rather than resetting, so only
    the presses too old to matter are dropped:

    >>> sliding = _InterruptCounter(window_s=5.0)
    >>> sliding.press(now=0.0)
    1
    >>> sliding.press(now=4.0)
    2
    >>> sliding.press(now=6.0)
    2

    A held key auto-repeats, resending presses faster than a human can
    release and press again. 'min_gap_s' collapses such a burst into the
    single logical press it represents:

    >>> held = _InterruptCounter(window_s=5.0, min_gap_s=0.3)
    >>> held.press(now=0.0)
    1
    >>> held.press(now=0.05)
    1
    >>> held.press(now=0.1)
    1
    >>> held.press(now=1.0)
    2
    """

    window_s: float
    min_gap_s: float = 0.0
    _presses: deque[float] = attrs.field(factory=deque, init=False)

    def press(self, now: float) -> int:
        assert not self._presses or now >= self._presses[-1], "'now' must not move backwards"

        if self._presses and now - self._presses[-1] < self.min_gap_s:
            return len(self._presses)

        self._presses.append(now)

        while self._presses[0] < now - self.window_s:
            self._presses.popleft()

        return len(self._presses)
