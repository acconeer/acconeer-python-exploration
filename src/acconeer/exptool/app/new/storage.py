from pathlib import Path
from uuid import uuid4

import platformdirs


def get_temp_dir() -> Path:
    et_dir = Path(platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB"))
    codename = "plugoneer"
    temp_dir = et_dir / codename / "temp"
    temp_dir.mkdir(parents=True)
    return temp_dir


def get_temp_h5_path() -> Path:
    return (get_temp_dir() / str(uuid4())).with_suffix(".h5")
