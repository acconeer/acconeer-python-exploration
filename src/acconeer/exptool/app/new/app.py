import logging
import sys

from PySide6 import QtCore
from PySide6.QtWidgets import QApplication

import pyqtgraph as pg

from .app_model import AppModel
from .backend import Backend
from .ui import MainWindow


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    backend = Backend()
    backend.start()

    model = AppModel(backend)
    model.start()

    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOption("leftButtonPan", False)
    pg.setConfigOptions(antialias=True)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)

    app = QApplication(sys.argv)

    app.setStyleSheet("")
    app.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    mw = MainWindow(model)
    mw.show()

    model.broadcast()

    app.exec()

    model.stop()
    backend.stop()
