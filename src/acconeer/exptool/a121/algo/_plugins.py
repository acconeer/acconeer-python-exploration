from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Callable, Generic, Optional, Type, TypeVar

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    AppModel,
    BackendPlugin,
    BusyMessage,
    ConnectionState,
    DataMessage,
    ErrorMessage,
    IdleMessage,
    KwargMessage,
    Message,
    OkMessage,
    PlotPlugin,
    PluginState,
    Task,
    ViewPlugin,
)
from acconeer.exptool.app.new.storage import get_temp_h5_path
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    HorizontalGroupBox,
    PidgetMapping,
    SessionConfigEditor,
)

from ._base import ProcessorBase


ConfigT = TypeVar("ConfigT")
ProcessorT = TypeVar("ProcessorT", bound=ProcessorBase)
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


class ProcessorBackendPluginBase(Generic[ConfigT, ProcessorT], BackendPlugin):
    _client: Optional[a121.Client]
    _processor_instance: Optional[ProcessorT]
    _recorder: Optional[a121.H5Recorder]
    _started: bool

    def __init__(self, callback: Callable[[Message], None], key: str):
        super().__init__(callback=callback, key=key)
        self._processor_instance = None
        self._client = None
        self._recorder = None
        self._started = False
        self._send_default_configs_to_view()

    def _send_default_configs_to_view(self) -> None:
        self.callback(
            DataMessage(
                "session_config",
                a121.SessionConfig(),
                recipient="view_plugin",
            )
        )
        self.callback(
            DataMessage(
                "processor_config",
                self.get_processor_config_cls()(),
                recipient="view_plugin",
            )
        )

    def idle(self) -> bool:
        if self._started:
            self._execute_get_next()
            return True
        else:
            return False

    def attach_client(self, *, client: a121.Client) -> None:
        self._client = client

    def detach_client(self) -> None:
        self._client = None

    def teardown(self) -> None:
        self.detach_client()

    def execute_task(self, *, task: Task) -> None:
        """Accepts the following tasks:

        -   (
                "start_session",
                {
                    session_config=a121.SessionConfig
                    processor_config=ProcessorConfig
                }
            ) -> [a121.Metadata, a121.SensorConfig]
        - ("stop_session", <Ignored>) -> None
        """
        task_name, task_kwargs = task
        if task_name == "start_session":
            try:
                self._execute_start(**task_kwargs)
            except Exception as e:
                self.callback(ErrorMessage("start_session", e))
                self.callback(IdleMessage())
        elif task_name == "stop_session":
            self._execute_stop()
        else:
            raise RuntimeError(f"Unknown task: {task_name}")

    def _execute_start(
        self,
        session_config: a121.SessionConfig,
        processor_config: ConfigT,
    ) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if not self._client.connected:
            # This check is here to avoid the
            # "auto-connect" behaviour in a121.Client.setup_session.
            raise RuntimeError("Client is not connected. Can not 'start'.")

        if session_config.extended:
            raise ValueError("Extended configs are not supported.")

        log.debug(f"SessionConfig has the update rate: {session_config.update_rate}")

        self.metadata = self._client.setup_session(session_config)
        assert isinstance(self.metadata, a121.Metadata)

        self._processor_instance = self.get_processor_cls()(
            sensor_config=session_config.sensor_config,
            metadata=self.metadata,
            processor_config=processor_config,
        )

        self.callback(DataMessage("saveable_file", None))
        self._recorder = a121.H5Recorder(get_temp_h5_path())
        algo_group = self._recorder.require_algo_group(self.key)  # noqa: F841

        # TODO: write processor_config etc. to algo group

        self._client.start_session(self._recorder)

        self._started = True

        self.callback(
            KwargMessage(
                "setup",
                dict(metadata=self.metadata, sensor_config=session_config.sensor_config),
                recipient="plot_plugin",
            )
        )
        self.callback(BusyMessage())

    def _execute_stop(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")

        self._client.stop_session()

        if self._recorder is not None:
            assert self._recorder.path is not None
            path = Path(self._recorder.path)
            self.callback(DataMessage("saveable_file", path))

        self._started = False

        self.callback(OkMessage("stop_session"))
        self.callback(IdleMessage())

    def _execute_get_next(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'get_next'.")
        if self._processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")

        result = self._client.get_next()
        assert isinstance(result, a121.Result)

        processor_result = self._processor_instance.process(result)
        self.callback(DataMessage("plot", processor_result, recipient="plot_plugin"))

    @classmethod
    @abc.abstractmethod
    def get_processor_cls(cls) -> Type[ProcessorT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
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
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.view_widget.setLayout(self.layout)

        self.start_button = QPushButton("Start measurement", self.view_widget)
        self.stop_button = QPushButton("Stop", self.view_widget)
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)

        button_group = HorizontalGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button)
        button_group.layout().addWidget(self.stop_button)

        self.layout.addWidget(button_group)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            pidget_mapping=self.get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.layout.addWidget(self.processor_config_editor)
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
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
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
