# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import os
from typing import Tuple, Union

import h5py


PathOrH5File = Union[str, os.PathLike, h5py.File]


def h5_file_factory(path_or_file: PathOrH5File, h5_file_mode: str) -> Tuple[h5py.File, bool]:
    """Constructs a `h5py.File` given an argument of type `PathOrFile`.

    If the argument already is a `h5py.File`, it's simply passed through.

    :returns: Tuple of (<h5py.File>, <whether the h5py.File was constructed in this function>)
    :raises: TypeError if `path_or_file` is an unsupported type.
    """
    if isinstance(path_or_file, h5py.File):
        return path_or_file, False
    elif isinstance(path_or_file, (os.PathLike, str)):
        path = path_or_file
        return h5py.File(path, mode=h5_file_mode), True
    else:
        raise TypeError(f"`path_or_file` was of unexpected type: {type(path_or_file)}")
