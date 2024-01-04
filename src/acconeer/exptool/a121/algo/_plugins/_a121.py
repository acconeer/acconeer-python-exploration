# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

import h5py

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    ApplicationClient,
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
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback, generation, key)
        self._live_client = None
        self._replaying_client = None
        self._opened_record = None

    @is_task
    def load_from_file(self, *, path: Path) -> None:
        try:
            self._opened_record = a121.H5Record(h5py.File(path, mode="r"))

            # This is to be able to replay files recorded before v7.0.0
            # when there were only one session per file
            if self._opened_record.num_sessions <= 1:
                replaying_client = a121._ReplayingClient(self._opened_record, cycled_session_idx=0)
            else:
                replaying_client = a121._ReplayingClient(self._opened_record)

            self.load_from_record_setup(record=self._opened_record)
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not load from file") from exc

        self._replaying_client = ApplicationClient.wrap_a121(replaying_client, self.callback)

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
        except KeyError:
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
                raise RuntimeError("Client is not attached. Can not 'get_next'.")

            try:
                self.get_next()
            except a121._StopReplay:
                self.stop_session()
                return True
            except Exception as exc:
                try:
                    self.stop_session()
                except Exception:
                    pass

                raise HandledException("Failed to get_next") from exc

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
        self._live_client = ApplicationClient.wrap_a121(client, self.callback)
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
            raise RuntimeError("Client is not attached. Can not 'start'.")

        if not self.client.connected:
            raise RuntimeError("Client is not connected. Can not 'start'.")

        self.callback(GeneralMessage(name="saveable_file", data=None))
        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
        else:
            self._recorder = None

        self.callback(PluginStateMessage(state=PluginState.LOADED_STARTING))
        try:
            self._start_session(self._recorder)
        except Exception as exc:
            recorder = self.client.detach_recorder()
            if recorder is not None:
                recorder.close()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start") from exc

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
            raise HandledException("Failure when stopping session") from exc
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
