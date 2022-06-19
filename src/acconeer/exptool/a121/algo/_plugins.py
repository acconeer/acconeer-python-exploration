from __future__ import annotations

import abc
import logging
from typing import Callable, Generic, TypeVar

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    AppModel,
    BackendPlugin,
    ConnectionState,
    KwargMessage,
    Message,
    PlotPlugin,
    PluginState,
    ViewPlugin,
)
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    HorizontalGroupBox,
    PidgetMapping,
    SessionConfigEditor,
)


ConfigT = TypeVar("ConfigT")
ResultT = TypeVar("ResultT")

log = logging.getLogger(__name__)


class NullAppModel(AppModel):
    class _NullSignal:
        def connect(self, slot: Callable) -> None:
            pass

    sig_notify: _NullSignal
    sig_error: _NullSignal
    sig_message_plot_plugin: _NullSignal

    def __init__(self) -> None:
        self.sig_notify = self._NullSignal()
        self.sig_error = self._NullSignal()
        self.sig_message_plot_plugin = self._NullSignal()


class DetectorBackendPluginBase(BackendPlugin):
    pass


class DetectorPlotPluginBase(PlotPlugin):
    pass


class DetectorViewPluginBase(ViewPlugin):
    pass


class ProcessorBackendPluginBase(BackendPlugin):
    pass


class ProcessorPlotPluginBase(Generic[ResultT], PlotPlugin):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        self._is_setup = False
        self._plot_job = None

    def handle_message(self, message: Message) -> None:
        if message.command_name == "setup":
            assert isinstance(message, KwargMessage)
            self.plot_layout.clear()
            self.setup(**message.kwargs)
            self._is_setup = True
        elif message.command_name == "plot":
            self._plot_job = message.data
        else:
            log.warn(
                f"{self.__class__.__name__} got an unsupported command: {message.command_name!r}."
            )

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        self.update(self._plot_job)
        self._plot_job = None

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass

    def on_app_model_error(self, exception: Exception) -> None:
        pass

    @abc.abstractmethod
    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        pass

    @abc.abstractmethod
    def update(self, processor_result: ResultT) -> None:
        pass


class ProcessorViewPluginBase(Generic[ConfigT], ViewPlugin):
    def __init__(self, view_widget: QWidget, app_model: AppModel) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        self.layout = QVBoxLayout(self.view_widget)
        self.view_widget.setLayout(self.layout)

        self.start_button = QPushButton("Start", self.view_widget)
        self.stop_button = QPushButton("Stop", self.view_widget)
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)

        button_group = HorizontalGroupBox("Processor controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button)
        button_group.layout().addWidget(self.stop_button)

        self.layout.addWidget(button_group)
        self.layout.addSpacing(10)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            pidget_mapping=self.get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.layout.addWidget(self.processor_config_editor)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.session_config_editor)
        self.layout.addStretch()

    def _send_start_requests(self) -> None:
        self.send_backend_task(
            (
                "start_session",
                {
                    "session_config": self.session_config_editor.session_config,
                    "processor_config": self.processor_config_editor.config,
                },
            )
        )
        self.send_backend_command(("set_idle_task", ("get_next", {})))
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.send_backend_command(("set_idle_task", None))
        self.send_backend_task(("stop_session", {}))
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def teardown(self) -> None:
        self.layout.deleteLater()

    def handle_message(self, message: Message) -> None:
        if message.command_name == "session_config":
            self.session_config_editor.session_config = message.data
        elif message.command_name == "processor_config":
            self.processor_config_editor.config = message.data
        else:
            raise ValueError(
                f"{self.__class__.__name__} cannot handle the message {message.command_name}"
            )

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.processor_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.start_button.setEnabled(
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def on_app_model_error(self, exception: Exception) -> None:
        pass

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetMapping:
        pass
