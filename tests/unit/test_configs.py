import multiprocessing as mp

import pytest

from acconeer.exptool import a111


def test_mode_to_config_map():
    set(a111.Mode.__members__) == set(a111._configs.MODE_TO_CONFIG_CLASS_MAP.keys())


def test_value_get_set():
    conf = a111.SparseServiceConfig()

    assert conf.downsampling_factor == 1
    conf.downsampling_factor = 2
    assert conf.downsampling_factor == 2
    del conf.downsampling_factor
    assert conf.downsampling_factor == 1


@pytest.mark.parametrize("mode", a111.Mode)
def test_value_dump_load(mode):
    config_cls = a111._configs.MODE_TO_CONFIG_CLASS_MAP[mode]
    config = config_cls()
    assert config.downsampling_factor == 1
    config.downsampling_factor = 2
    dump = config._dumps()

    config = config_cls()
    assert config.downsampling_factor == 1
    config._loads(dump)
    assert config.downsampling_factor == 2

    another_mode = next(other_mode for other_mode in a111.Mode if other_mode != mode)
    another_config_cls = a111._configs.MODE_TO_CONFIG_CLASS_MAP[another_mode]

    config = another_config_cls()
    with pytest.raises(AssertionError):
        config._loads(dump)


def dump_fun(config):
    return config._dumps()


def test_mp():
    conf = a111.SparseServiceConfig()
    conf.downsampling_factor = 2
    [dump] = mp.Pool(1).map(dump_fun, [conf])
    assert dump == conf._dumps()
