from .backend import Backend
from .ui import run_with_backend


def main():
    backend = Backend()

    backend.start()

    run_with_backend(backend)

    backend.stop()
