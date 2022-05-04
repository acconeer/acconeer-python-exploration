# type: ignore

import pytest

from acconeer.exptool.a121._core import utils


def test_convert_validate_int_ok_value():
    _ = utils.convert_validate_int(3)
    _ = utils.convert_validate_int(3.0)


def test_convert_validate_int_type_errors():
    with pytest.raises(TypeError):
        _ = utils.convert_validate_int("3")

    with pytest.raises(TypeError):
        _ = utils.convert_validate_int(3.5)


def test_convert_validate_int_boundaries():
    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(0, min_value=1)

    with pytest.raises(ValueError):
        _ = utils.convert_validate_int(1, max_value=0)


def test_validate_float_ok_value():
    _ = utils.validate_float(3.1)
    _ = utils.validate_float(3.1, max_value=3.1)
    _ = utils.validate_float(3.1, min_value=3.1)
    _ = utils.validate_float(3.1, min_value=3.0, max_value=3.2)


def test_validate_float_type_errors():
    with pytest.raises(TypeError):
        _ = utils.validate_float("3.1")


def test_validate_float_boundaries():
    with pytest.raises(ValueError):
        _ = utils.validate_float(0.0, min_value=1.0)

    with pytest.raises(ValueError):
        _ = utils.validate_float(1.0, max_value=0.0)

    with pytest.raises(ValueError):
        _ = utils.validate_float(0.0, max_value=0.0, inclusive=False)

    with pytest.raises(ValueError):
        _ = utils.validate_float(0.1, min_value=0.0, max_value=0.1, inclusive=False)


class Wrappee:
    def __init__(self):
        self._rw_property = 10

    @property
    def ro_property(self) -> int:
        """RO docstring"""
        return 5

    @property
    def rw_property(self) -> int:
        """RW docstring"""
        return self._rw_property

    @rw_property.setter
    def rw_property(self, value) -> None:
        self._rw_property = value


class Wrapper:
    ro_property = utils.ProxyProperty[int](
        lambda wrapper: wrapper.get_first(), Wrappee.ro_property
    )
    rw_property = utils.ProxyProperty[int](
        lambda wrapper: wrapper.get_first(), Wrappee.rw_property
    )

    def __init__(self, wrappee):
        self.wrappees = [wrappee]

    def get_first(self):
        return self.wrappees[0]


def test_proxy_descriptor():
    wrappee = Wrappee()
    wrapper = Wrapper(wrappee)

    assert wrappee.ro_property == wrapper.ro_property == 5

    # The proxy property should repsect read-only
    with pytest.raises(AttributeError):
        wrapper.ro_property = 5

    assert wrapper.rw_property == wrappee.rw_property == 10

    wrapper.rw_property = 20
    assert wrapper.rw_property == wrappee.rw_property == 20

    wrappee.rw_property = 10
    assert wrapper.rw_property == wrappee.rw_property == 10


def test_proxy_descriptor_preserves_docstring():
    assert Wrappee.ro_property.__doc__ == Wrapper.ro_property.__doc__ == "RO docstring"


def test_proxy_descriptor_edge_cases():
    with pytest.raises(TypeError):

        class Wrapper2:
            wrong_type = utils.ProxyProperty[int](lambda wrapper: wrapper.get_first(), prop=3)


def test_unextend():
    argument = [{1: "test"}]
    assert utils.unextend(argument) == "test"


def test_unextend_bad_argument():
    argument = ["test"]
    with pytest.raises(ValueError):
        utils.unextend(argument)
