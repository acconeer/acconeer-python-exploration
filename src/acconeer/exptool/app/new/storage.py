# Copyright (c) Acconeer AB, 2022
# All rights reserved

import shutil
from pathlib import Path
from uuid import uuid4

import platformdirs


ET_DIR = Path(platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB"))
CODENAME = "plugoneer"
CONFIG_DIR = ET_DIR / CODENAME / "config"
TEMP_DIR = ET_DIR / CODENAME / "temp"


def get_config_dir() -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


def remove_config_dir() -> None:
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)


def get_temp_dir() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def remove_temp_dir() -> None:
    shutil.rmtree(TEMP_DIR, ignore_errors=True)


def get_temp_h5_path() -> Path:
    return (get_temp_dir() / str(uuid4())).with_suffix(".h5")
