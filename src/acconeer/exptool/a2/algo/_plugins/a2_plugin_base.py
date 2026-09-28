# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import abc
import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Generic, Sequence, TypeVar

import h5py

from PySide6.QtWidgets import QLabel

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import Criticality, ValidationResult
from acconeer.exptool.a2._core.recording.replaying_client import ReplayingClient
from acconeer.exptool.app.new import (
    ApplicationClient,
    AppModel,
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
from acconeer.exptool.app.new.ui import icons


log = logging.getLogger(__name__)


T = TypeVar("T")


def _has_errors(validation_results: Sequence[ValidationResult]) -> bool:
    return any(result.criticality == Criticality.ERROR for result in validation_results)


class A2BackendPluginBase(Generic[T], BackendPlugin[T]):
    _live_client: a2.Client | None
    _replaying_client: a2.Client | None
    _opened_record: a2.H5Record | None
    _started: bool = False
    _recorder: a2.H5Recorder | None = None

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ) -> None:
        super().__init__(callback, generation, key)
        self._live_client = None
        self._replaying_client = None
        self._opened_record = None
        self._logger = BackendLogger.getLogger(__name__)
        # Defaults to the plugin's own key; a subclass whose recordings
        # share an algo group with a sibling plugin (e.g. two variants of
        # the same app) overrides this to that shared group name.
        self._algo_group_key = key

    @is_task
    def load_from_file(
        self,
        *,
        path: Path,
        config_override: Any | None = None,
        context_override: Any | None = None,
    ) -> None:
        try:
            self._opened_record = a2.open_record(path)

            replaying_client = ReplayingClient(self._opened_record)

            self.load_from_record_setup(
                record=self._opened_record,
                config_override=config_override,
                context_override=context_override,
            )
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            msg = "Could not load from file"
            raise HandledException(msg) from exc
        else:
            self._replaying_client = ApplicationClient.wrap_a2(replaying_client, self.callback)
            self.start_session(with_recorder=False)
            self.send_status_message(f"<b>Replaying from {path.name}</b>")
            self.broadcast()

    @abc.abstractmethod
    def load_from_record_setup(
        self,
        *,
        record: a2.H5Record,
        config_override: Any | None = None,
        context_override: Any | None = None,
    ) -> None:
        pass

    @is_task
    def load_from_cache(self) -> None:
        try:
            with self.h5_cache_file() as f:
                self.shared_state = self._load_from_cache(f)
        except FileNotFoundError:
            pass
        except Exception as exc:
            self._logger.warning(f"Could not load the cached configuration, using defaults: {exc}")
            self._logger.debug(traceback.format_exc())
            self.send_status_message("Could not load the saved configuration, using defaults.")

        self.broadcast()

    @abc.abstractmethod
    def _load_from_cache(self, file: h5py.File) -> T:
        """The current state with what the cache holds applied"""
        pass

    @abc.abstractmethod
    def get_next(self) -> None:
        pass

    def idle(self) -> bool:
        if not self._started:
            return False

        if self.client is None:
            msg = "Client is not attached. Can not 'get_next'."
            raise RuntimeError(msg)

        try:
            self.get_next()
        except StopIteration:
            self.stop_session()
        except Exception as exc:
            try:
                self.stop_session()
            except Exception:
                self._logger.exception(exc)

            msg = "Failed to get_next"
            raise HandledException(msg) from exc

        return True

    @property
    def client(self) -> a2.Client | None:
        if self._replaying_client is not None:
            return self._replaying_client
        else:
            return self._live_client

    def _sync_sensor_ids(self) -> None:
        pass

    def attach_client(self, *, client: a2.Client) -> None:
        self._live_client = ApplicationClient.wrap_a2(client, self.callback)
        self._sync_sensor_ids()
        self.broadcast()

    def detach_client(self) -> None:
        self._live_client = None

    @abc.abstractmethod
    def _start_session(self, recorder: a2.H5Recorder | None) -> None:
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
            self._recorder = a2.H5Recorder(get_temp_h5_path())
            self._recorder.require_algo_group(self._algo_group_key)
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
            msg = "Could not start"
            raise HandledException(msg) from exc

        self._started = True

        self.broadcast()

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if not self._started:
            # Such as when a replay has just ended on its own
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
            self._opened_record.close()
            self._opened_record = None
            self._replaying_client = None
            self._sync_sensor_ids()

    def teardown(self) -> None:
        try:
            with self.h5_cache_file(write=True) as file:
                self.save_to_cache(file)
        except Exception as e:
            log.warning("Could not write to cache")
            log.debug(e, exc_info=True, stack_info=True)

        self.detach_client()

    @abc.abstractmethod
    def save_to_cache(self, file: h5py.File) -> None:
        pass


class A2ViewPluginBase(ViewPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        self._config_is_valid = True
        self.invalid_config_note = QLabel("Invalid configuration, see the errors below.")
        self.invalid_config_note.setWordWrap(True)
        self.invalid_config_note.setContentsMargins(5, 5, 5, 5)
        self.invalid_config_note.setStyleSheet(
            f"background-color: {icons.ERROR_RED}; color: white; font: bold italic;"
        )
        self.invalid_config_note.hide()

    def _update_config_validity(self, validation_results: Sequence[ValidationResult]) -> None:
        self._config_is_valid = not _has_errors(validation_results)

    def _config_ready(self, no_gui_errors: bool) -> bool:
        """Whether the configuration can start, showing the note when it cannot"""
        ready = no_gui_errors and self._config_is_valid
        self.invalid_config_note.setHidden(ready)
        return ready

    def _send_start_request(self) -> None:
        A2BackendPluginBase.start_session.rpc(
            self.app_model.put_task,
            with_recorder=self.app_model.recording_enabled,
        )

    def _send_stop_request(self) -> None:
        A2BackendPluginBase.stop_session.rpc(self.app_model.put_task)
