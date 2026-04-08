# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

import shutil
from pathlib import Path
from uuid import uuid4

import platformdirs


DEFAULT_ET_DIR = Path(
    platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB")
)
ET_DIR = DEFAULT_ET_DIR

CODENAME = "plugoneer"


def _config_dir() -> Path:
    return ET_DIR / CODENAME / "config"


def _temp_dir() -> Path:
    return ET_DIR / CODENAME / "temp"


def set_et_dir(path: Path) -> None:
    """
    Set the ET directory to be used by ET application.

    The ET directory decides where plugin cache & not-yet-saved records will be saved.
    """
    global ET_DIR

    ET_DIR = path


def get_config_dir() -> Path:
    config_dir = _config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def remove_config_dir() -> None:
    shutil.rmtree(_config_dir(), ignore_errors=True)


def get_temp_dir() -> Path:
    temp_dir = _temp_dir()
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def remove_temp_dir() -> None:
    shutil.rmtree(_temp_dir(), ignore_errors=True)


def get_temp_h5_path() -> Path:
    return (get_temp_dir() / str(uuid4())).with_suffix(".h5")
