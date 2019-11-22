from acconeer.exptool import modes, configs


def test_mode_to_config_map():
    set(modes.Mode.__members__) == set(configs.MODE_TO_CONFIG_CLASS_MAP.keys())
