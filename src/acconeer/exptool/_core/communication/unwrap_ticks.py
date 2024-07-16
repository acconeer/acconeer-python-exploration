# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

from typing import Optional, Tuple


def unwrap_ticks(
    ticks: list[int], minimum_tick: Optional[int], limit: int = 2**32
) -> Tuple[list[int], Optional[int]]:
    """Unwraps a sequence of ticks belonging to a collection of result

    The server tick (attached to produced Results) wraps at 2^32 (uint32_t). Thus, if the raw tick is
    used for evaluating the time between two results, it will be incorrect if a wrap has occurred
    between them. Therefore, it has to be accounted for by "unwrapping".

    Wrapping can occur between the results in an extended result, and that the results are not
    necessarily ordered by the tick. This means that we have to look at all the ticks produced in
    the extended result at the same time.

    For example:

    Let's say that the most recent tick we saw was 70 and the wrap happens at limit = 100. Given 2 results
    with ticks 10 and 90; it's more likely that 10 has wrapped than not, we assume it's
    actually after 90, i.e., 110:

    >>> unwrap_ticks([10, 90], minimum_tick=70, limit=100)
    ([110, 90], ...)

    Now, let's also consider that the previous maximum unwrapped tick was 195, which is now the
    'minimum tick'. From this, we know that the ticks have wrapped before and can account for that,
    resulting in the final unwrapped ticks of 310 and 290. The new minimum tick will then be 310:

    >>> unwrap_ticks([10, 90], minimum_tick=195, limit=100)
    ([310, 290], 310)
    """

    if len(ticks) == 0:
        return [], None

    if any(tick < 0 or tick >= limit for tick in ticks):
        msg = "Tick value out of bounds"
        raise ValueError(msg)

    if (max(ticks) - min(ticks)) > limit // 2:
        ticks = [tick + limit if tick < limit // 2 else tick for tick in ticks]

    if minimum_tick is not None:
        num_wraps = max((minimum_tick - tick - 1) // limit + 1 for tick in ticks)
        ticks = [num_wraps * limit + tick for tick in ticks]

    return ticks, max(ticks)
