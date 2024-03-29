# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from . import a111, utils
from ._core.communication.comm_devices import USBDevice
from ._structs import configbase
from .pg_process import PGProccessDiedException, PGProcess


try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0"
