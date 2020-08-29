import multiprocessing as mp

import pytest

from acconeer.exptool import configs, modes


def test_mode_to_config_map():
    set(modes.Mode.__members__) == set(configs.MODE_TO_CONFIG_CLASS_MAP.keys())


def test_value_get_set():
    conf = configs.SparseServiceConfig()

    assert conf.downsampling_factor == 1
    conf.downsampling_factor = 2
    assert conf.downsampling_factor == 2
    del conf.downsampling_factor
    assert conf.downsampling_factor == 1


@pytest.mark.parametrize("mode", modes.Mode)
def test_value_dump_load(mode):
    config_cls = configs.MODE_TO_CONFIG_CLASS_MAP[mode]
    config = config_cls()
    assert config.downsampling_factor == 1
    config.downsampling_factor = 2
    dump = config._dumps()

    config = config_cls()
    assert config.downsampling_factor == 1
    config._loads(dump)
    assert config.downsampling_factor == 2

    another_mode = next(other_mode for other_mode in modes.Mode if other_mode != mode)
    another_config_cls = configs.MODE_TO_CONFIG_CLASS_MAP[another_mode]

    config = another_config_cls()
    with pytest.raises(AssertionError):
        config._loads(dump)


def dump_fun(config):
    return config._dumps()


def test_mp():
    conf = configs.SparseServiceConfig()
    conf.downsampling_factor = 2
    [dump] = mp.Pool(1).map(dump_fun, [conf])
    assert dump == conf._dumps()
