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


def test_value_dump_load():
    conf = configs.SparseServiceConfig()
    assert conf.downsampling_factor == 1
    conf.downsampling_factor = 2
    dump = conf._dumps()

    conf = configs.SparseServiceConfig()
    assert conf.downsampling_factor == 1
    conf._loads(dump)
    assert conf.downsampling_factor == 2

    conf = configs.EnvelopeServiceConfig()
    with pytest.raises(AssertionError):
        conf._loads(dump)


def dump_fun(config):
    return config._dumps()


def test_mp():
    conf = configs.SparseServiceConfig()
    conf.downsampling_factor = 2
    [dump] = mp.Pool(1).map(dump_fun, [conf])
    assert dump == conf._dumps()
