import pytest

from acconeer.exptool.a121 import _utils as utils


def test_convert_validate_int_ok_value():
    _ = utils.convert_validate_int(3)
    _ = utils.convert_validate_int(3.0)


def test_convert_validate_int_type_errors():
    with pytest.raises(TypeError):
        _ = utils.convert_validate_int("3")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        _ = utils.convert_validate_int(3.5)


def test_convert_validate_int_boundaries():
    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(0, min_value=1)

    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(1, max_value=0)
