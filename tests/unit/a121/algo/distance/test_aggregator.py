# Copyright (c) Acconeer AB, 2023
# All rights reserved

import numpy as np
import pytest

from acconeer.exptool.a121.algo import distance


def test_merge_peaks() -> None:
    min_distance = 1
    distances = np.array([0.0, 2.0, 4.0, 5.0])
    strengths = np.array([0.0, 0.0, 1.0, 2.0])
    (actual_dists_merged, actual_strengths_merged,) = distance.Aggregator._merge_peaks(
        min_peak_to_peak_dist=min_distance, dists=distances, strengths=strengths
    )

    assert actual_dists_merged[0] == pytest.approx(distances[0])
    assert actual_dists_merged[1] == pytest.approx(distances[1])
    assert actual_dists_merged[2] == pytest.approx(4.5)

    assert actual_strengths_merged[0] == pytest.approx(strengths[0])
    assert actual_strengths_merged[1] == pytest.approx(strengths[1])
    assert actual_strengths_merged[2] == pytest.approx(1.5)
