# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import pytest

from acconeer.exptool import a2
from acconeer.exptool.a2.algo._utils import PRF_MMD_TABLE, get_prf_for_end_m


def test_prf_mmd_table_is_ordered_highest_to_lowest_prf() -> None:
    """``get_prf_for_end_m`` returns the first covering entry, so it relies on
    this order."""
    frequencies = [prf.frequency for prf in PRF_MMD_TABLE]
    mmds_m = list(PRF_MMD_TABLE.values())

    assert set(PRF_MMD_TABLE) == set(a2.PRF)
    assert frequencies == sorted(frequencies, reverse=True)
    assert mmds_m == sorted(mmds_m)
    assert len(set(mmds_m)) == len(mmds_m)


@pytest.mark.parametrize(
    ("end_m", "profile", "expected"),
    [
        (2.4, a2.Profile.PROFILE_6, a2.PRF.PRF_27_7_MHZ),
        (2.4, a2.Profile.PROFILE_7, a2.PRF.PRF_20_8_MHZ),
        (2.5, a2.Profile.PROFILE_6, a2.PRF.PRF_20_8_MHZ),
    ],
)
def test_get_prf_for_end_m(end_m: float, profile: a2.Profile, expected: a2.PRF) -> None:
    assert get_prf_for_end_m(end_m, profile=profile) is expected


def test_get_prf_for_end_m_raises_beyond_lowest_prf_mmd() -> None:
    with pytest.raises(ValueError, match=r"^No PRF covers end_m=25\.1 m\.$"):
        get_prf_for_end_m(25.1, profile=a2.Profile.PROFILE_7)
