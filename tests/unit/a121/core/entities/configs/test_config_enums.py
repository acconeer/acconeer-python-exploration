# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool import a121


def test_prf_frequencies() -> None:
    assert a121.PRF.PRF_13_0_MHz.frequency == 13e6


def test_profile_init() -> None:
    assert (
        a121.Profile.PROFILE_1
        == a121.Profile(a121.Profile.PROFILE_1)
        == a121.Profile(1)
        == a121.Profile("PROFILE_1")
    )


def test_prf_init() -> None:
    assert (
        a121.PRF.PRF_13_0_MHz
        == a121.PRF(a121.PRF.PRF_13_0_MHz)
        == a121.PRF(13e6)
        == a121.PRF("PRF_13_0_MHz")
    )


def test_idle_state_init() -> None:
    assert (
        a121.IdleState.DEEP_SLEEP
        == a121.IdleState(a121.IdleState.DEEP_SLEEP)
        == a121.IdleState("DEEP_SLEEP")
        == a121.IdleState("deep_sleep")
    )


def test_idle_state_comparison() -> None:
    """This asserts that "depth" of IdleStates can be correctly compared"""

    assert a121.IdleState.DEEP_SLEEP.is_deeper_than(a121.IdleState.SLEEP)
    assert a121.IdleState.SLEEP.is_deeper_than(a121.IdleState.READY)
