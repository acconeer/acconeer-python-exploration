# Copyright (c) Acconeer AB, 2023
# All rights reserved

import pytest

from acconeer.exptool._core.communication.unwrap_ticks import unwrap_ticks


@pytest.mark.parametrize(
    ("ticks", "minimum_tick", "expected_ticks"),
    [
        ([0], None, [0]),
        ([99], None, [99]),
        ([40, 60], None, [40, 60]),
        ([90, 0], None, [90, 100]),
        ([90, 10], None, [90, 110]),
        ([10], 0, [10]),
        ([10], 209, [210]),
        ([10], 210, [210]),
        ([10], 211, [310]),
        ([10, 90], 185, [210, 190]),
        ([10, 90], 195, [310, 290]),
    ],
)
def test_unwrap_ticks_normal_cases(ticks, minimum_tick, expected_ticks):
    expected = (expected_ticks, max(expected_ticks))
    assert unwrap_ticks(ticks, minimum_tick, limit=100) == expected


def test_unwrap_ticks_special_cases():
    assert unwrap_ticks([], None) == ([], None)

    with pytest.raises(Exception):
        unwrap_ticks([-1], None, limit=100)

    with pytest.raises(Exception):
        unwrap_ticks([100], None, limit=100)
