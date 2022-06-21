from __future__ import annotations

import abc
import logging
import traceback
from pathlib import Path
from typing import Callable, Generic, Optional, Type, TypeVar

import attrs
import h5py

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
    GridGroupBox,
    PidgetMapping,
    SessionConfigEditor,
)

from ._base import AlgoConfigBase, ProcessorBase


ConfigT = TypeVar("ConfigT", bound=AlgoConfigBase)
ProcessorT = TypeVar("ProcessorT", bound=ProcessorBase)
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")

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


@attrs.mutable(kw_only=True)
class ProcessorBackendPluginSharedState(Generic[ConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ConfigT = attrs.field()
    replaying: bool = attrs.field(default=False)


class ProcessorBackendPluginBase(
    Generic[ConfigT, ProcessorT], BackendPlugin[ProcessorBackendPluginSharedState[ConfigT]]
):
    _live_client: Optional[a121.Client]
    _processor_instance: Optional[ProcessorT]
    _recorder: Optional[a121.H5Recorder]
    _started: bool
    _opened_file: Optional[h5py.File]
    _opened_record: Optional[a121.H5Record]
    _replaying_client: Optional[a121.ReplayingClient]

    def __init__(self, callback: Callable[[Message], None], key: str):
        super().__init__(callback=callback, key=key)
        self._processor_instance = None
        self._live_client = None
        self._recorder = None
        self._started = False
        self._replaying_client = None
        self._opened_file = False
        self._opened_record = None

        self._restore_defaults()

    def broadcast(self, sync: bool = False) -> None:
        super().broadcast()

        if sync:
            self.callback(OkMessage("sync", recipient="view_plugin"))

    def _restore_defaults(self) -> None:
        self.shared_state = ProcessorBackendPluginSharedState[ConfigT](
            session_config=a121.SessionConfig(self.get_default_sensor_config()),
            processor_config=self.get_processor_config_cls()(),
        )

        self.broadcast(sync=True)

    @property
    def _client(self) -> Optional[a121.Client]:
        if self._replaying_client is not None:
            return self._replaying_client

        return self._live_client

    def idle(self) -> bool:
        if self._started:
            self._execute_get_next()
            return True
        else:
            return False

    def attach_client(self, *, client: a121.Client) -> None:
        self._live_client = client

    def detach_client(self) -> None:
        self._live_client = None

    def teardown(self) -> None:
        self.detach_client()

    def load_from_file(self, *, path: Path) -> None:
        self._opened_file = h5py.File(path, mode="r")
        self._opened_record = a121.H5Record(self._opened_file)
        self._replaying_client = a121.ReplayingClient(self._opened_record)

        self.shared_state.session_config = self._opened_record.session_config

        try:
            algo_group = self._opened_record.get_algo_group(self.key)  # noqa: F841
            # TODO: break out loading (?)
            self.shared_state.processor_config = self.get_processor_config_cls().from_json(
                algo_group["processor_config"][()]
            )
        except Exception:
            log.warning(f"Could not load '{self.key}' from file")

        self.shared_state.replaying = True

        self.broadcast(sync=True)

        try:
            self._execute_start(with_recorder=False)
        except Exception as e:
            self.callback(ErrorMessage("start_session", e, traceback_str=traceback.format_exc()))
            self.callback(IdleMessage())

    def execute_task(self, *, task: Task) -> None:
        """Accepts the following tasks:

        - ("start_session", <Ignored>) -> None
        - ("stop_session", <Ignored>) -> None
        """
        task_name, task_kwargs = task
        if task_name == "start_session":
            try:
                self._execute_start()
            except Exception as e:
                self.callback(
                    ErrorMessage("start_session", e, traceback_str=traceback.format_exc())
                )
                self.callback(IdleMessage())
        elif task_name == "stop_session":
            self._execute_stop()
        elif task_name == "restore_defaults":
            self._restore_defaults()
        elif task_name == "update_session_config":
            session_config = task_kwargs["session_config"]
            assert isinstance(session_config, a121.SessionConfig)
            self.shared_state.session_config = session_config
            self.broadcast()
        elif task_name == "update_processor_config":
            processor_config = task_kwargs["processor_config"]
            assert isinstance(processor_config, self.get_processor_config_cls())
            self.shared_state.processor_config = processor_config
            self.broadcast()
        else:
            raise RuntimeError(f"Unknown task: {task_name}")

    def _execute_start(self, *, with_recorder: bool = True) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if not self._client.connected:
            # This check is here to avoid the
            # "auto-connect" behaviour in a121.Client.setup_session.
            raise RuntimeError("Client is not connected. Can not 'start'.")

        session_config = self.shared_state.session_config

        if session_config.extended:
            raise ValueError("Extended configs are not supported.")

        log.debug(f"SessionConfig has the update rate: {session_config.update_rate}")

        metadata = self._client.setup_session(session_config)
        assert isinstance(metadata, a121.Metadata)

        self._processor_instance = self.get_processor_cls()(
            sensor_config=session_config.sensor_config,
            metadata=metadata,
            processor_config=self.shared_state.processor_config,
        )

        self.callback(DataMessage("saveable_file", None))
        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
            algo_group = self._recorder.require_algo_group(self.key)  # noqa: F841

            # TODO: break out saving (?)
            algo_group.create_dataset(
                "processor_config",
                data=self.shared_state.processor_config.to_json(),
                dtype=a121.H5PY_STR_DTYPE,
                track_times=False,
            )
        else:
            self._recorder = None

        self._client.start_session(self._recorder)

        self._started = True

        self.callback(
            KwargMessage(
                "setup",
                dict(metadata=metadata, sensor_config=session_config.sensor_config),
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

        if self.shared_state.replaying:
            assert self._opened_record is not None
            self._opened_record.close()

            self._opened_file = None
            self._opened_record = None
            self._replaying_client = None

            self.shared_state.replaying = False

        self._started = False

        self.broadcast()
        self.callback(IdleMessage())

    def _execute_get_next(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'get_next'.")
        if self._processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")

        try:
            result = self._client.get_next()
        except a121.StopReplay:
            self._execute_stop()
            return

        assert isinstance(result, a121.Result)

        if result.data_saturated:
            self.send_status_message(self._format_warning("Data saturated - reduce gain"))

        if result.calibration_needed:
            self.send_status_message(self._format_warning("Calibration needed - restart"))

        if result.frame_delayed:
            self.send_status_message(self._format_warning("Frame delayed"))

        processor_result = self._processor_instance.process(result)
        self.callback(DataMessage("plot", processor_result, recipient="plot_plugin"))

    @classmethod
    def _format_warning(cls, s: str) -> str:
        return f'<p style="color: #FD5200;"><b>Warning: {s}</b></p>'

    @classmethod
    @abc.abstractmethod
    def get_processor_cls(cls) -> Type[ProcessorT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
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
        self.defaults_button = QPushButton("Restore default settings", self.view_widget)
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)
        self.defaults_button.clicked.connect(self._send_defaults_request)

        button_group = GridGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.defaults_button, 1, 0, 1, 2)

        self.layout.addWidget(button_group)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.session_config_editor.sig_update.connect(self._on_session_config_update)
        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            pidget_mapping=self.get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        self.layout.addWidget(self.processor_config_editor)
        self.layout.addWidget(self.session_config_editor)
        self.layout.addStretch()

    def _on_session_config_update(self, session_config: a121.SessionConfig) -> None:
        self.send_backend_task(("update_session_config", {"session_config": session_config}))

    def _on_processor_config_update(self, processor_config: ConfigT) -> None:
        self.send_backend_task(("update_processor_config", {"processor_config": processor_config}))

    def _send_start_requests(self) -> None:
        self.send_backend_task(("start_session", {}))
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.send_backend_task(("stop_session", {}))
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _send_defaults_request(self) -> None:
        self.send_backend_task(("restore_defaults", {}))

    def teardown(self) -> None:
        self.layout.deleteLater()

    def handle_message(self, message: Message) -> None:
        if message.command_name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.session_config_editor.sync()
            self.processor_config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.processor_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.start_button.setEnabled(
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)
        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        if app_model.backend_plugin_state is None:
            self.session_config_editor.set_data(None)
            self.processor_config_editor.set_data(None)
        else:
            assert isinstance(app_model.backend_plugin_state, ProcessorBackendPluginSharedState)
            assert isinstance(
                app_model.backend_plugin_state.processor_config, self.get_processor_config_cls()
            )

            self.session_config_editor.set_data(app_model.backend_plugin_state.session_config)
            self.processor_config_editor.set_data(app_model.backend_plugin_state.processor_config)

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
        pass
