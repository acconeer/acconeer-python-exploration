from acconeer.exptool import configs, modes


def test_mode_to_config_map():
    set(modes.Mode.__members__) == set(configs.MODE_TO_CONFIG_CLASS_MAP.keys())
