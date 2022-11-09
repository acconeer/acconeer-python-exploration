# Copyright (c) Acconeer AB, 2022
# All rights reserved

from . import a111, utils
from ._structs import configbase
from .pg_process import PGProccessDiedException, PGProcess
from .utils import USBDevice


try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0"
