SDK_VERSION = "2.10.0"

from . import a111
from .pg_process import PGProccessDiedException, PGProcess
from .structs import configbase


try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0.0"
