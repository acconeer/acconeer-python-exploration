# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from . import _qt_bindings_canary, a111, utils
from ._core.communication.comm_devices import USBDevice, get_usb_devices
from ._processes.pg_process import PGProccessDiedException, PGProcess
from ._structs import configbase


try:
    # hatch-vcs/setuptools_scm generated version file
    from ._version import __version__
except ImportError as ie:
    msg = "Could not locate version file. Try reinstalling acconeer-exptool."
    raise ImportError(msg) from ie
