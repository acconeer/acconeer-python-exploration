# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

import ctypes
import importlib.resources
import sys
import typing as t

import qdarktheme

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QApplication

import pyqtgraph as pg

from acconeer.exptool.app import resources
from acconeer.exptool.utils import config_logging

from ._argument_parser import ExptoolArgumentParser
from .app_model import AppModel
from .backend import Backend
from .plugin_loader import import_and_register_plugin_module, load_plugins
from .storage import remove_config_dir, remove_temp_dir
from .ui import AppModelViewer, MainWindow


def main() -> None:
    parser = ExptoolArgumentParser()
    args = parser.parse_args()
    config_logging(args)

    if args.purge_config:
        remove_config_dir()
        remove_temp_dir()
        print("Config purged")
        sys.exit(0)

    if sys.platform == "win32" or sys.platform == "cygwin":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("acconeer.exptool")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )

    # The cast necessitated of a miss in the typing stubs.
    app: QApplication = t.cast(QApplication, QApplication.instance()) or QApplication(sys.argv)

    app.setStyleSheet(qdarktheme.load_stylesheet("light"))
    app.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    if args.plugin_modules is not None:
        for plugin_module_name in args.plugin_modules:
            import_and_register_plugin_module(plugin_module_name)

    backend = Backend()
    backend.start()

    model = AppModel(backend, load_plugins())
    model.start()

    app.aboutToQuit.connect(model.stop)
    app.aboutToQuit.connect(backend.stop)

    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOption("leftButtonPan", False)
    pg.setConfigOptions(antialias=True)

    with importlib.resources.path(resources, "icon.png") as path:
        app.setWindowIcon(_pixmap_to_icon(QtGui.QPixmap(str(path))))

    mw = MainWindow(model)
    mw.show()

    if args.amv:
        app_model_viewer = AppModelViewer(model)
        app_model_viewer.show()
        mw.sig_closing.connect(app_model_viewer.close)

    model.broadcast()

    sys.exit(app.exec())


def _pixmap_to_icon(pixmap: QtGui.QPixmap) -> QtGui.QIcon:
    size = max(pixmap.size().height(), pixmap.size().width())

    square_pixmap = QtGui.QPixmap(size, size)
    square_pixmap.fill(QtGui.QRgba64.fromRgba(0, 0, 0, 0))

    painter = QtGui.QPainter(square_pixmap)
    painter.drawPixmap(
        (square_pixmap.size().width() - pixmap.size().width()) // 2,
        (square_pixmap.size().height() - pixmap.size().height()) // 2,
        pixmap,
    )
    painter.end()

    scaled_pixmap = square_pixmap.scaled(
        256,
        256,
        aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        mode=QtGui.Qt.TransformationMode.SmoothTransformation,
    )

    return QtGui.QIcon(scaled_pixmap)
