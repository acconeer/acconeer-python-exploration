# Copyright (c) Acconeer AB, 2022
# All rights reserved

import h5py

from acconeer.exptool import a121


def _create_h5_string_dataset(group: h5py.Group, name: str, string: str) -> None:
    group.create_dataset(
        name,
        data=string,
        dtype=a121._H5PY_STR_DTYPE,
        track_times=False,
    )
