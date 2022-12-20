# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
import logging
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

import h5py

import pyqtgraph as pg

from acconeer.exptool import a121
from acconeer.exptool.app.new import (
    AppModel,
    BackendPlugin,
    GeneralMessage,
    HandledException,
    Message,
    PlotPluginBase,
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
    _replaying_client: Optional[a121._ReplayingClient]
    _opened_record: Optional[a121.H5Record]
    _started: bool = False
    _recorder: Optional[a121.H5Recorder] = None
    _frame_count: int

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback, generation, key)
        self._live_client = None
        self._replaying_client = None
        self._opened_record = None
        self._frame_count = 0

    @is_task
    def load_from_file(self, *, path: Path) -> None:
        try:
            self._opened_record = a121.H5Record(h5py.File(path, mode="r"))
            self._replaying_client = a121._ReplayingClient(self._opened_record)
            self.load_from_record_setup(record=self._opened_record)
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not load from file") from exc

        self.start_session(with_recorder=False)

        self.send_status_message(f"<b>Replaying from {path.name}</b>")
        self.broadcast(sync=True)

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

        self._sync_sensor_ids()
        self.broadcast(sync=True)

    @abc.abstractmethod
    def _load_from_cache(self, file: h5py.File) -> None:
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
    def client(self) -> Optional[a121.ClientBase]:
        if self._replaying_client is not None:
            return self._replaying_client

        return self._live_client

    @abc.abstractmethod
    def _sync_sensor_ids(self) -> None:
        pass

    def attach_client(self, *, client: a121.Client) -> None:
        self._live_client = client
        self._sync_sensor_ids()
        self.broadcast(True)

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

        try:
            self._start_session(self._recorder)
        except Exception as exc:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start") from exc

        self._started = True

        self.broadcast()

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if not self._started:
            raise RuntimeError

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
            self._frame_count = 0
            self.broadcast()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            self.callback(GeneralMessage(name="rate_stats", data=None))
            self.callback(GeneralMessage(name="frame_count", data=None))

        if self._opened_record:
            self._opened_record.close()
            self._opened_record = None
            self._replaying_client = None

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
    pass


class A121PlotPluginBase(PlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        self._is_setup = False
        self._plot_job: Optional[GeneralMessage] = None

    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "setup":
            self.plot_layout.clear()
            self.setup_from_message(message)
            self._is_setup = True
        elif message.name == "plot":
            self._plot_job = message
        else:
            log.warn(f"{self.__class__.__name__} got an unsupported command: {message.name!r}.")

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        try:
            self.update_from_message(self._plot_job)
        finally:
            self._plot_job = None

    @abc.abstractmethod
    def setup_from_message(self, message: GeneralMessage) -> None:
        pass

    @abc.abstractmethod
    def update_from_message(self, message: GeneralMessage) -> None:
        pass
