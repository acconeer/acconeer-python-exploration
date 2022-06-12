import importlib_metadata

from PySide6 import QtCore
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin_loader import load_default_plugins

from .connection_widget import ClientConnectionWidget, GenerationSelection
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


class TopBar(QFrame):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setObjectName("TopBar")
        self.setStyleSheet("QFrame#TopBar {background: #ebebeb;}")

        self.setLayout(QHBoxLayout(self))

        self.layout().addWidget(GenerationSelection(app_model, self))
        self.layout().addWidget(ClientConnectionWidget(app_model, self))
        self.layout().addStretch(1)


class WorkingArea(QSplitter):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        graphics_layout_widget = pg.GraphicsLayoutWidget()

        left_area = LeftArea(app_model, self, graphics_layout_widget)
        self.layout().addWidget(left_area)
        self.layout().setStretchFactor(left_area, 0)

        self.layout().addWidget(graphics_layout_widget)
        self.layout().setStretchFactor(graphics_layout_widget, 1)

        right_area = RightArea(app_model, self)
        self.layout().addWidget(right_area)
        self.layout().setStretchFactor(right_area, 0)


class LeftArea(QScrollArea):
    def __init__(
        self,
        app_model: AppModel,
        parent: QWidget,
        graphics_layout_widget: pg.GraphicsLayoutWidget,  # TODO: remove
    ) -> None:
        super().__init__(parent)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.horizontalScrollBar().setEnabled(False)

        self.setMinimumWidth(250)
        self.setMaximumWidth(350)

        self.setWidget(LeftAreaContent(app_model, self, graphics_layout_widget))


class LeftAreaContent(QWidget):
    def __init__(
        self,
        app_model: AppModel,
        parent: QWidget,
        graphics_layout_widget: pg.GraphicsLayoutWidget,  # TODO: remove
    ) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))

        plugin_control_widget = PluginControlWidget(
            app_model,
            graphics_layout_widget,  # TODO: remove
            load_default_plugins(),  # TODO: remove
            parent=self,  # TODO: remove kwarg
        )
        self.layout().addWidget(plugin_control_widget)

        self.layout().addStretch(1)


class RightArea(QScrollArea):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.horizontalScrollBar().setEnabled(False)

        self.setMinimumWidth(300)
        self.setMaximumWidth(400)

        self.setWidget(RightAreaContent(app_model, self))


class RightAreaContent(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))

        placeholder_label = QLabel(self)
        self.layout().addWidget(placeholder_label)
        placeholder_label.setText("Right bar placeholder")

        self.layout().addStretch(1)


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        et_version = importlib_metadata.version("acconeer-exptool")
        et_version_text = f"ET: {et_version}"
        self.addPermanentWidget(QLabel(et_version_text, self))
