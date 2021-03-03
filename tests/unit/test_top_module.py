import functools

import pytest

import acconeer.exptool as pet
from acconeer.exptool import clients, configs, modes, structs


def is_test(member_name, modules):
    """ the `is` operator is reference equality, while `==` is for "member equality"
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
    "client_type",
    ["UARTClient", "SPIClient", "SocketClient", "PollingUARTClient", "MockClient"],
)
def test_top_module_clients(client_type):
    assert pet.clients == clients
    assert is_test(client_type, [pet, clients, pet.clients])


@pytest.mark.parametrize(
    "config_type",
    [
        "EnvelopeServiceConfig",
        "IQServiceConfig",
        "PowerBinServiceConfig",
        "SparseServiceConfig",
    ]
)
def test_top_module_configs(config_type):
    assert pet.configs == configs
    assert is_test(config_type, [pet, configs, pet.configs])


@pytest.mark.parametrize("structs_member", ["configbase"])
def test_top_module_structs(structs_member):
    assert is_test(structs_member, [pet, structs, pet.structs])


def test_top_module_mode():
    assert is_test("Mode", [pet, modes])
