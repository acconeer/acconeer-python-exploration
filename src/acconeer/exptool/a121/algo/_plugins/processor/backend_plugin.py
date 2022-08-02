from __future__ import annotations

import abc
import logging
import pickle
from pathlib import Path
from typing import Callable, Generic, Optional, Type, TypeVar

import attrs
import h5py

from acconeer.exptool import a121
from acconeer.exptool.a121.algo import AlgoConfigBase, ProcessorBase
from acconeer.exptool.a121.algo._plugins._a121 import A121BackendPluginBase
from acconeer.exptool.app.new import (
    GeneralMessage,
    HandledException,
    Message,
    PluginGeneration,
    PluginState,
    PluginStateMessage,
    is_task,
)
from acconeer.exptool.app.new.storage import get_temp_h5_path


ConfigT = TypeVar("ConfigT", bound=AlgoConfigBase)
ProcessorT = TypeVar("ProcessorT", bound=ProcessorBase)

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
