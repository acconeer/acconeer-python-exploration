from __future__ import annotations

import abc
import logging
import pickle
from pathlib import Path
from typing import Callable, Generic, Optional, Type, TypeVar

import attrs
import h5py
import qtawesome as qta

from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoConfigBase, ProcessorBase
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    ConnectionState,
    GeneralMessage,
    HandledException,
    Message,
    PluginGeneration,
    PluginState,
    PluginStateMessage,
    is_task,
)
from acconeer.exptool.app.new.storage import get_temp_h5_path
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    GridGroupBox,
    PerfCalcView,
    PidgetFactoryMapping,
    SessionConfigEditor,
    SmartMetadataView,
)

from ._a121 import A121BackendPluginBase, A121PlotPluginBase, A121ViewPluginBase


ConfigT = TypeVar("ConfigT", bound=AlgoConfigBase)
ProcessorT = TypeVar("ProcessorT", bound=ProcessorBase)
ResultT = TypeVar("ResultT")
StateT = TypeVar("StateT")

log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class ProcessorBackendPluginSharedState(Generic[ConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ConfigT = attrs.field()
    replaying: bool = attrs.field(default=False)
    metadata: Optional[a121.Metadata] = attrs.field(default=None)

    @property
    def ready(self):
        try:
            self.session_config.validate()
        except a121.ValidationError:
            return False
        else:
            return True


@attrs.frozen(kw_only=True)
class ProcessorSave(Generic[ConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ConfigT = attrs.field()


class ProcessorBackendPluginBase(
    Generic[ConfigT, ProcessorT], A121BackendPluginBase[ProcessorBackendPluginSharedState[ConfigT]]
):
    _live_client: Optional[a121.Client]
    _processor_instance: Optional[ProcessorT]
    _recorder: Optional[a121.H5Recorder]
    _started: bool
    _opened_file: Optional[h5py.File]
    _opened_record: Optional[a121.H5Record]
    _replaying_client: Optional[a121._ReplayingClient]

    def __init__(self, callback: Callable[[Message], None], key: str):
        super().__init__(callback=callback, key=key)
        self._processor_instance = None
        self._live_client = None
        self._recorder = None
        self._started = False
        self._replaying_client = None
        self._opened_file = None
        self._opened_record = None

        self.restore_defaults()

    @is_task
    def deserialize(self, *, data: bytes) -> None:
        try:
            obj = pickle.loads(data)
        except Exception:
            log.warning("Could not load pickled - pickle.loads() failed")
            return

        if not isinstance(obj, ProcessorSave):
            log.warning("Could not load pickled - not the correct type")
            return

        if not isinstance(obj.processor_config, self.get_processor_config_cls()):
            log.warning("Could not load pickled - not the correct type")
            return

        self.shared_state.session_config = obj.session_config
        self.shared_state.processor_config = obj.processor_config
        self.broadcast(sync=True)

    def _serialize(self) -> bytes:
        obj = ProcessorSave(
            session_config=self.shared_state.session_config,
            processor_config=self.shared_state.processor_config,
        )
        return pickle.dumps(obj, protocol=4)

    def broadcast(self, sync: bool = False) -> None:
        super().broadcast()

        if sync:
            self.callback(GeneralMessage(name="sync", recipient="view_plugin"))

    @is_task
    def restore_defaults(self) -> None:
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
            self._get_next()
            return True
        else:
            return False

    def attach_client(self, *, client: a121.Client) -> None:
        self._live_client = client

    def detach_client(self) -> None:
        self._live_client = None

    def teardown(self) -> None:
        self.callback(
            GeneralMessage(
                name="serialized",
                kwargs={
                    "generation": PluginGeneration.A121,
                    "key": self.key,
                    "data": self._serialize(),
                },
            )
        )
        self.detach_client()

    @is_task
    def load_from_file(self, *, path: Path) -> None:
        try:
            self._load_from_file_setup(path=path)
        except Exception as exc:
            self._opened_file = None
            self._opened_record = None
            self._replaying_client = None
            self.shared_state.replaying = False

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not load from file") from exc

        self.start_session(with_recorder=False)

        self.shared_state.replaying = True

        self.send_status_message(f"<b>Replaying from {path.name}</b>")
        self.broadcast(sync=True)

    def _load_from_file_setup(self, *, path: Path) -> None:
        self._opened_file = h5py.File(path, mode="r")
        self._opened_record = a121.H5Record(self._opened_file)
        self._replaying_client = a121._ReplayingClient(self._opened_record)

        self.shared_state.session_config = self._opened_record.session_config

        try:
            algo_group = self._opened_record.get_algo_group(self.key)  # noqa: F841
            # TODO: break out loading (?)
            self.shared_state.processor_config = self.get_processor_config_cls().from_json(
                algo_group["processor_config"][()]
            )
        except Exception:
            log.warning(f"Could not load '{self.key}' from file")

    @is_task
    def update_session_config(self, *, session_config: a121.SessionConfig) -> None:
        self.shared_state.session_config = session_config
        self.broadcast()

    @is_task
    def update_processor_config(self, *, processor_config: ConfigT) -> None:
        self.shared_state.processor_config = processor_config
        self.broadcast()

    @is_task
    def start_session(self, *, with_recorder: bool = True) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if not self._client.connected:
            # This check is here to avoid the
            # "auto-connect" behaviour in a121.Client.setup_session.
            raise RuntimeError("Client is not connected. Can not 'start'.")

        session_config = self.shared_state.session_config
        if session_config.extended:
            raise ValueError("Extended configs are not supported.")

        self.callback(GeneralMessage(name="saveable_file", data=None))
        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
            algo_group = self._recorder.require_algo_group(self.key)  # noqa: F841

            # TODO: break out saving (?)
            algo_group.create_dataset(
                "processor_config",
                data=self.shared_state.processor_config.to_json(),
                dtype=a121._H5PY_STR_DTYPE,
                track_times=False,
            )
        else:
            self._recorder = None

        try:
            metadata = self._client.setup_session(session_config)
            assert isinstance(metadata, a121.Metadata)

            self._client.start_session(self._recorder)
        except a121.ServerError as exc:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start session: " + str(exc)) from exc
        except Exception as exc:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start session") from exc

        self._processor_instance = self.get_processor_cls()(
            sensor_config=session_config.sensor_config,
            metadata=metadata,
            processor_config=self.shared_state.processor_config,
        )

        self._started = True

        self.shared_state.metadata = metadata
        self.broadcast()

        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(metadata=metadata, sensor_config=session_config.sensor_config),
                recipient="plot_plugin",
            )
        )
        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")

        try:
            self._client.stop_session()
        except Exception as exc:
            raise HandledException("Failure when stopping session") from exc
        finally:
            if self._recorder is not None:
                assert self._recorder.path is not None
                path = Path(self._recorder.path)
                self.callback(GeneralMessage(name="saveable_file", data=path))

            if self.shared_state.replaying:
                assert self._opened_record is not None
                self._opened_record.close()

                self._opened_file = None
                self._opened_record = None
                self._replaying_client = None

                self.shared_state.replaying = False

            self._started = False

            self.shared_state.metadata = None
            self.broadcast()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            self.callback(GeneralMessage(name="result_tick_time", data=None))

    def _get_next(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'get_next'.")
        if self._processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")

        try:
            result = self._client.get_next()
            assert isinstance(result, a121.Result)
        except a121._StopReplay:
            self.stop_session()
            return
        except Exception as exc:
            try:
                self.stop_session()
            except Exception:
                pass

            raise HandledException("Failed to get_next") from exc

        if result.data_saturated:
            self.send_status_message(self._format_warning("Data saturated - reduce gain"))

        if result.calibration_needed:
            self.send_status_message(self._format_warning("Calibration needed - restart"))

        if result.frame_delayed:
            self.send_status_message(self._format_warning("Frame delayed"))

        processor_result = self._processor_instance.process(result)
        self.callback(GeneralMessage(name="result_tick_time", data=result.tick_time))
        self.callback(GeneralMessage(name="plot", data=processor_result, recipient="plot_plugin"))

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


class ProcessorPlotPluginBase(Generic[ResultT], A121PlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        self.update(message.data)  # type: ignore[arg-type]

    @abc.abstractmethod
    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        pass

    @abc.abstractmethod
    def update(self, processor_result: ResultT) -> None:
        pass


class ProcessorViewPluginBase(Generic[ConfigT], A121ViewPluginBase):
    def __init__(self, view_widget: QWidget, app_model: AppModel) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        self.layout = QVBoxLayout(self.view_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.view_widget.setLayout(self.layout)

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.view_widget,
        )
        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.view_widget,
        )
        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Restore default settings",
            self.view_widget,
        )
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)
        self.defaults_button.clicked.connect(self._send_defaults_request)

        button_group = GridGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.defaults_button, 1, 0, 1, 2)

        self.layout.addWidget(button_group)

        self.metadata_view = SmartMetadataView(self.view_widget)
        self.layout.addWidget(self.metadata_view)

        self.perf_calc_view = PerfCalcView(self.view_widget)
        self.layout.addWidget(self.perf_calc_view)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.session_config_editor.sig_update.connect(self._on_session_config_update)
        self.processor_config_editor = AttrsConfigEditor[ConfigT](
            title="Processor parameters",
            factory_mapping=self.get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.processor_config_editor.sig_update.connect(self._on_processor_config_update)
        self.layout.addWidget(self.processor_config_editor)
        self.layout.addWidget(self.session_config_editor)
        self.layout.addStretch()

    def _on_session_config_update(self, session_config: a121.SessionConfig) -> None:
        self.app_model.put_backend_plugin_task(
            "update_session_config", {"session_config": session_config}
        )

    def _on_processor_config_update(self, processor_config: ConfigT) -> None:
        self.app_model.put_backend_plugin_task(
            "update_processor_config", {"processor_config": processor_config}
        )

    def _send_start_requests(self) -> None:
        self.app_model.put_backend_plugin_task("start_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    def teardown(self) -> None:
        self.layout.deleteLater()

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
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
            and app_model.backend_plugin_state.ready
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)
        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        if app_model.backend_plugin_state is None:
            self.session_config_editor.set_data(None)
            self.processor_config_editor.set_data(None)
            self.metadata_view.update(None)
            self.perf_calc_view.update()
        else:
            assert isinstance(app_model.backend_plugin_state, ProcessorBackendPluginSharedState)
            assert isinstance(
                app_model.backend_plugin_state.processor_config, self.get_processor_config_cls()
            )

            self.session_config_editor.set_data(app_model.backend_plugin_state.session_config)
            self.processor_config_editor.set_data(app_model.backend_plugin_state.processor_config)
            self.metadata_view.update(app_model.backend_plugin_state.metadata)
            self.perf_calc_view.update(
                app_model.backend_plugin_state.session_config,
                app_model.backend_plugin_state.metadata,
            )

        self.session_config_editor.update_available_sensor_list(app_model._a121_server_info)

    @classmethod
    @abc.abstractmethod
    def get_pidget_mapping(cls) -> PidgetFactoryMapping:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ConfigT]:
        pass
