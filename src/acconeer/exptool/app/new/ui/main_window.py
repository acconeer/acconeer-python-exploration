from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin_loader import load_default_plugins

from .connection_widget import ClientConnectionWidget
from .plugin_widget import PluginControlWidget


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        self.backend = app_model._backend  # TODO: remove access to backend
        self.setup_ui()

    def setup_ui(self) -> None:
        main_layout = QHBoxLayout()

        self.lhs_layout = QVBoxLayout()
        lhs_dummy = QWidget()
        lhs_dummy.setProperty("acc_type", "lhs")
        lhs_dummy.setLayout(self.lhs_layout)

        self.plot_layout_widget = pg.GraphicsLayoutWidget()
        self.lhs_layout.addWidget(self.plot_layout_widget)

        self.rhs_layout = QVBoxLayout()
        rhs_dummy = QWidget()
        rhs_dummy.setProperty("acc_type", "rhs")
        rhs_dummy.setLayout(self.rhs_layout)
        self.rhs_layout.addWidget(ClientConnectionWidget(self.backend))
        self.rhs_layout.addWidget(
            PluginControlWidget(self.backend, self.plot_layout_widget, load_default_plugins())
        )

        main_layout.addWidget(lhs_dummy)
        main_layout.addWidget(rhs_dummy)

        dummy = QWidget()
        dummy.setLayout(main_layout)
        self.setCentralWidget(dummy)
