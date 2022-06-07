import logging
import sys

from .backend import Backend
from .ui import run_with_backend


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    backend = Backend()

    backend.start()

    run_with_backend(backend)

    backend.stop()
