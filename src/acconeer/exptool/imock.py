import builtins
import unittest.mock


def import_mock_wrapper(name, *args, **kwargs):
    try:
        return original_import(name, *args, **kwargs)
    except ModuleNotFoundError:
        package = name.split(".")[0].lower()
        if package in mock_packages:
            return unittest.mock.MagicMock()

        raise


def add_mock_packages(packages):
    mock_packages.update([p.lower() for p in packages])


mock_packages = set()
original_import = builtins.__import__
builtins.__import__ = import_mock_wrapper

GRAPHICS_LIBS = [
    "matplotlib",
    "pyqtgraph",
    "pyqt5",
]
