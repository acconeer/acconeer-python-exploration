import numpy as np
import pytest

from acconeer.exptool.a121.algo import distance


def test_merge_peaks():
    min_distance = 1
    distances = np.array([0.0, 2.0, 4.0, 5.0])
    amplitudes = np.array([1.0, 1.0, 1.0, 2.0])
    (actual_dists_merged, actual_ampls_merged) = distance.Aggregator._merge_peaks(
        min_peak_to_peak_dist=min_distance, dists=distances, ampls=amplitudes
    )

    assert actual_dists_merged[0] == pytest.approx(distances[0])
    assert actual_dists_merged[1] == pytest.approx(distances[1])
    assert actual_dists_merged[2] == pytest.approx(4.5)

    assert actual_ampls_merged[0] == pytest.approx(amplitudes[0])
    assert actual_ampls_merged[1] == pytest.approx(amplitudes[1])
    assert actual_ampls_merged[2] == pytest.approx(1.5)
