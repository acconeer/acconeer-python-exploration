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

from acconeer.exptool.app.new.app_model import AppModel

from .connection_widget import ClientConnectionWidget, GenerationSelection
from .flash_widget import FlashButton
from .misc import ExceptionWidget
from .plugin_widget import PluginControlArea, PluginPlotArea, PluginSelection
from .recording_widget import RecordingWidget


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        self.setCentralWidget(MainWindowCentralWidget(app_model, self))
        self.setStatusBar(StatusBar(app_model, self))
        self.setWindowTitle("Acconeer Exploration Tool (Beta)")

        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_error(self, exception: Exception) -> None:
        ExceptionWidget(self, exc=exception).exec()


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
        self.layout().addWidget(FlashButton(app_model, self))
        self.layout().addStretch(1)
        self.layout().addWidget(RecordingWidget(app_model, self))


class WorkingArea(QSplitter):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QHBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        left_area = LeftArea(app_model, self)
        self.layout().addWidget(left_area)
        self.layout().setStretchFactor(left_area, 0)

        plot_plugin_area = PluginPlotArea(app_model, self)
        self.layout().addWidget(plot_plugin_area)
        self.layout().setStretchFactor(plot_plugin_area, 1)

        right_area = RightArea(app_model, self)
        self.layout().addWidget(right_area)
        self.layout().setStretchFactor(right_area, 0)


class LeftArea(QScrollArea):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.horizontalScrollBar().setEnabled(False)

        self.setMinimumWidth(250)
        self.setMaximumWidth(350)

        self.setWidget(LeftAreaContent(app_model, self))


class LeftAreaContent(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.setLayout(QVBoxLayout(self))

        self.layout().addWidget(PluginSelection(app_model, self))

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

        self.layout().addWidget(PluginControlArea(app_model, self))


class StatusBar(QStatusBar):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        app_model.sig_notify.connect(self._on_app_model_update)

        self.rss_version_label = QLabel(self)
        self.addPermanentWidget(self.rss_version_label)

        et_version = importlib_metadata.version("acconeer-exptool")
        et_version_text = f"ET: {et_version}"
        self.addPermanentWidget(QLabel(et_version_text, self))

    def _on_app_model_update(self, app_model: AppModel) -> None:
        if app_model.rss_version is None:
            css = "color: #888;"
            text = "RSS: <not connected>"
        else:
            css = ""
            text = f"RSS: {app_model.rss_version}"

        self.rss_version_label.setStyleSheet(css)
        self.rss_version_label.setText(text)
