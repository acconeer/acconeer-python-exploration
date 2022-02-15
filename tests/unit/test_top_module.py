import functools

import pytest

import acconeer.exptool as et
from acconeer.exptool import structs
from acconeer.exptool.a111 import _configs, _modes


def is_test(member_name, modules):
    """the `is` operator is reference equality, while `==` is for "member equality"
    i.e. 2 different objects have the same contents.

    We want to verify that one member `is` the same across namespaces.
    """
    # Gets the same member from different modules
    members = [getattr(module, member_name) for module in modules]

    # if `a is b`, `a` is safe as a reduction.
    # if `a is not b` then None will be the reduction
    # (and also the final reduction)
    def _is(a, b):
        return a if (a is b) else None

    return functools.reduce(_is, members) is not None


@pytest.mark.parametrize(
    "config_type",
    [
        "EnvelopeServiceConfig",
        "IQServiceConfig",
        "PowerBinServiceConfig",
        "SparseServiceConfig",
    ],
)
def test_top_module_configs(config_type):
    assert et.a111._configs == _configs
    assert is_test(config_type, [et.a111, _configs, et.a111._configs])


@pytest.mark.parametrize("structs_member", ["configbase"])
def test_top_module_structs(structs_member):
    assert is_test(structs_member, [et, structs, et.structs])


def test_top_module_mode():
    assert is_test("Mode", [et.a111, _modes])
