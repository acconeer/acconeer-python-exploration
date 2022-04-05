import pytest

from acconeer.exptool import a121


@pytest.mark.xfail(reason="Not implemented yet")
def test_init_default_values():
    ssc = a121.SubsweepConfig()

    assert ssc.hwaas == 1  # type: ignore[attr-defined]


@pytest.mark.xfail(reason="Not implemented yet")
def test_init_with_arguments():
    ssc = a121.SubsweepConfig(hwaas=4)  # type: ignore[call-arg]

    assert ssc.hwaas == 4  # type: ignore[attr-defined]
