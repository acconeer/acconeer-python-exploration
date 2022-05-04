from acconeer.exptool import a121


def test_prf_frequencies():
    assert (
        a121.PRF.PRF_13_0_MHz.frequency
        == a121.PRF.PRF_13_0_MHz.value
        == a121.PRF.PRF_13_0_MHz
        == 13e6
    )


def test_profile_init():
    assert (
        a121.Profile.PROFILE_1
        == a121.Profile(a121.Profile.PROFILE_1)
        == a121.Profile(1)
        == a121.Profile("PROFILE_1")  # type: ignore[arg-type]
    )


def test_prf_init():
    assert (
        a121.PRF.PRF_13_0_MHz
        == a121.PRF(a121.PRF.PRF_13_0_MHz)
        == a121.PRF(13e6)  # type: ignore[arg-type]
        == a121.PRF("PRF_13_0_MHz")  # type: ignore[arg-type]
    )


def test_idle_state_init():
    assert (
        a121.IdleState.DEEP_SLEEP
        == a121.IdleState(a121.IdleState.DEEP_SLEEP)
        == a121.IdleState("DEEP_SLEEP")  # type: ignore[arg-type]
        == a121.IdleState("deep_sleep")  # type: ignore[arg-type]
    )


def test_idle_state_order():
    """This asserts that "depth" of IdleStates can be correctly compared.
    Deeper <=> lower value.
    """
    assert a121.IdleState.DEEP_SLEEP < a121.IdleState.SLEEP
    assert a121.IdleState.SLEEP < a121.IdleState.READY
