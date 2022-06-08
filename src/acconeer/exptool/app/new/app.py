import logging
import sys

from PySide6.QtWidgets import QApplication

from .app_model import AppModel
from .backend import Backend
from .ui import MainWindow


def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    backend = Backend()
    backend.start()

    model = AppModel(backend)
    model.start()

    app = QApplication(sys.argv)

    app.setStyleSheet(
        """
        *[acc_type="rhs"] { background-color: #e6a595 }
        *[acc_type="lhs"] { background-color: #a3c9ad }
        """
    )

    mw = MainWindow(model)
    mw.show()
    app.exec()

    model.stop()
    backend.stop()
