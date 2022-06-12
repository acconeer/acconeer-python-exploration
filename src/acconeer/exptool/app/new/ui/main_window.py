from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QStatusBar, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin_loader import load_default_plugins

from .connection_widget import ClientConnectionWidget
from .plugin_widget import PluginControlWidget


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1200, 800)

        self.setCentralWidget(MainWindowCentralWidget(app_model, self))
        self.setStatusBar(StatusBar(app_model, self))


class MainWindowCentralWidget(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        top_bar = TopBar(app_model, self)
        self.layout().addWidget(top_bar)
        self.layout().setStretchFactor(top_bar, 0)

        working_area = WorkingArea(app_model, self)
        self.layout().addWidget(working_area)
        self.layout().setStretchFactor(working_area, 1)


class TopBar(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))

        self.layout().addWidget(ClientConnectionWidget(app_model, self))
        self.layout().addStretch(1)


class WorkingArea(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        graphics_layout_widget = pg.GraphicsLayoutWidget()

        self.layout().addWidget(LeftBar(app_model, self, graphics_layout_widget))
        self.layout().addWidget(graphics_layout_widget)
        self.layout().addWidget(RightBar(app_model, self))


class LeftBar(QWidget):
    def __init__(
        self,
        app_model: AppModel,
        parent: QWidget,
        graphics_layout_widget: pg.GraphicsLayoutWidget,  # TODO: remove
    ) -> None:
        super().__init__(parent)

        self.setStyleSheet("background-color: #a3c9ad;")  # TODO: remove

        self.setLayout(QHBoxLayout(self))

        plugin_control_widget = PluginControlWidget(
            app_model,
            graphics_layout_widget,  # TODO: remove
            load_default_plugins(),  # TODO: remove
            parent=self,  # TODO: remove kwarg
        )
        self.layout().addWidget(plugin_control_widget)

        self.layout().addStretch(1)


class RightBar(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setStyleSheet("background-color: #e6a595;")  # TODO: remove

        self.setLayout(QHBoxLayout(self))

        placeholder_label = QLabel(self)
        self.layout().addWidget(placeholder_label)
        placeholder_label.setText("Right bar placeholder")

        self.layout().addStretch(1)


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.showMessage("Status bar placeholder")
