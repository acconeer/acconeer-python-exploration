# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import abc
import logging
import re
from pathlib import Path
from typing import Any, Callable, Generic, Optional, TypeVar

import h5py
from packaging.version import Version

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    ApplicationClient,
    BackendLogger,
    BackendPlugin,
    GeneralMessage,
    HandledException,
    Message,
    PluginGeneration,
    PluginState,
    PluginStateMessage,
    ViewPluginBase,
    get_temp_h5_path,
    is_task,
)


log = logging.getLogger(__name__)


T = TypeVar("T")


class A121BackendPluginBase(Generic[T], BackendPlugin[T]):
    _live_client: Optional[a121.Client]
    _replaying_client: Optional[a121.Client]
    _opened_record: Optional[a121.H5Record]
    _started: bool = False
    _recorder: Optional[a121.H5Recorder] = None

    def __init__(
        self,
        callback: Callable[[Message], None],
        generation: PluginGeneration,
        key: str,
        use_app_client: bool = True,
    ) -> None:
        super().__init__(callback, generation, key)
        self._live_client = None
        self._replaying_client = None
        self._opened_record = None
        self._logger = BackendLogger.getLogger(__name__)
        self._use_app_client = use_app_client

    @is_task
    def load_from_file(
        self,
        *,
        path: Path,
        config_override: Optional[Any] = None,
        context_override: Optional[Any] = None,
    ) -> None:
        if config_override is not None:
            self._logger.warning(f"Ignoring config override of type: {type(config_override)}")
        if context_override is not None:
            self._logger.warning(f"Ignoring context override of type: {type(context_override)}")

        try:
            self._opened_record = a121.H5Record(h5py.File(path, mode="r"))

            log_version_match = re.match(
                "^([0-9]+[.][0-9]+[.][0-9]+)[.]", self._opened_record.lib_version
            )
            if log_version_match is None:
                log_version = "0.0.0"  # assume old/any version
            else:
                log_version = log_version_match.groups()[0]

            # This is to be able to replay files recorded before v7.0.0
            # when there were only one session per file
            if self._opened_record.num_sessions <= 1 and Version(log_version) < Version("7.0.0"):
                replaying_client = a121._ReplayingClient(self._opened_record, cycled_session_idx=0)
            else:
                replaying_client = a121._ReplayingClient(self._opened_record)

            self.load_from_record_setup(record=self._opened_record)
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            msg = "Could not load from file"

            # Add more details from exception thrown
            for exc_arg in exc.args:
                if isinstance(exc_arg, str):
                    msg += f", {exc_arg}"

            raise HandledException(msg) from exc
        if self._use_app_client:
            self._replaying_client = ApplicationClient.wrap_a121(replaying_client, self.callback)
        else:
            self._replaying_client = replaying_client

        self.start_session(with_recorder=False)

        self.send_status_file_access_message(f"{path.name}", opened=True)
        self.broadcast()

    @abc.abstractmethod
    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        pass

    @is_task
    def load_from_cache(self) -> None:
        try:
            with self.h5_cache_file() as f:
                self._load_from_cache(f)
        except FileNotFoundError:
            pass
        except Exception:
            log.warning("Cache file loading failed, using defaults")
            self.restore_defaults()

        self._sync_sensor_ids()
        self.broadcast()

    @abc.abstractmethod
    def _load_from_cache(self, file: h5py.File) -> None:
        pass

    @is_task
    @abc.abstractmethod
    def restore_defaults(self) -> None:
        pass

    @abc.abstractmethod
    def get_next(self) -> None:
        pass

    def idle(self) -> bool:
        if self._started:
            if self.client is None:
                msg = "Client is not attached. Can not 'get_next'."
                raise RuntimeError(msg)

            try:
                self.get_next()
            except (a121._StopReplay, a121.ReplaySessionsExhaustedError):
                self.stop_session()
                return True
            except Exception as exc:
                try:
                    self.stop_session()
                except Exception as e:
                    self._logger.exception(e)

                msg = "Failed to get_next"
                raise HandledException(msg) from exc

            return True
        else:
            return False

    @property
    def client(self) -> Optional[a121.Client]:
        if self._replaying_client is not None:
            return self._replaying_client

        return self._live_client

    @abc.abstractmethod
    def _sync_sensor_ids(self) -> None:
        pass

    def attach_client(self, *, client: a121.Client) -> None:
        if self._use_app_client:
            self._live_client = ApplicationClient.wrap_a121(client, self.callback)
        else:
            self._live_client = client
        self._sync_sensor_ids()
        self.broadcast()

    def detach_client(self) -> None:
        self._live_client = None

    @abc.abstractmethod
    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        pass

    @abc.abstractmethod
    def end_session(self) -> None:
        pass

    @is_task
    def start_session(self, *, with_recorder: bool = True) -> None:
        if self._started:
            raise RuntimeError

        if self.client is None:
            msg = "Client is not attached. Can not 'start'."
            raise RuntimeError(msg)

        if not self.client.connected:
            msg = "Client is not connected. Can not 'start'."
            raise RuntimeError(msg)

        self.callback(GeneralMessage(name="saveable_file", data=None))
        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
        else:
            self._recorder = None

        self.callback(PluginStateMessage(state=PluginState.LOADED_STARTING))
        try:
            self._start_session(self._recorder)
        except Exception as exc:
            msg = "Could not start"
            # Add more details from exception thrown
            for exc_arg in exc.args:
                if isinstance(exc_arg, str):
                    msg += f", {exc_arg}"

            recorder = self.client.detach_recorder()
            if recorder is not None:
                recorder.close()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException(msg) from exc

        self._started = True

        self.broadcast()

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if not self._started:
            log.debug("Not stopping. Session was not started")
            return

        self.callback(PluginStateMessage(state=PluginState.LOADED_STOPPING))
        try:
            self.end_session()
        except Exception as exc:
            msg = "Failure when stopping session"
            raise HandledException(msg) from exc
        finally:
            if self._recorder is not None:
                assert self._recorder.path is not None
                path = Path(self._recorder.path)
                self.callback(GeneralMessage(name="saveable_file", data=path))
                self._recorder = None

            self._started = False
            self.broadcast()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        if self._opened_record:
            self.send_status_file_access_message(
                f"{self._opened_record.file.filename}", opened=False
            )
            self._opened_record.close()
            self._opened_record = None
            self._replaying_client = None
            self._sync_sensor_ids()

    def teardown(self) -> None:
        try:
            with self.h5_cache_file(write=True) as file:
                self.save_to_cache(file)
        except Exception:
            log.warning("Could not write to cache")

        self.detach_client()

    @abc.abstractmethod
    def save_to_cache(self, file: h5py.File) -> None:
        pass


class A121ViewPluginBase(ViewPluginBase):
    def _send_start_request(self) -> None:
        A121BackendPluginBase.start_session.rpc(
            self.app_model.put_task,
            with_recorder=self.app_model.recording_enabled,
        )

    def _send_stop_request(self) -> None:
        A121BackendPluginBase.stop_session.rpc(self.app_model.put_task)
