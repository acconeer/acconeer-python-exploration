# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import abc
from typing import Callable, Generic, Mapping, Optional, Type

import attrs
import h5py

from acconeer.exptool import a121
from acconeer.exptool.a121 import _core
from acconeer.exptool.a121._h5_utils import _create_h5_string_dataset
from acconeer.exptool.a121.algo._base import (
    GenericProcessorBase,
    InputT,
    MetadataT,
    ProcessorConfigT,
    ResultT,
)
from acconeer.exptool.a121.algo._plugins._a121 import A121BackendPluginBase
from acconeer.exptool.app.new import (
    BackendLogger,
    GeneralMessage,
    Message,
    PluginGeneration,
    is_task,
)


CALIBRATION_NEEDED_MESSAGE = "Calibration needed - restart"
DATA_SATURATED_MESSAGE = "Data saturated - reduce gain"
FRAME_DELAYED_MESSAGE = "Frame delayed"


@attrs.mutable(kw_only=True)
class ProcessorPluginPreset(Generic[ProcessorConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ProcessorConfigT = attrs.field()


@attrs.mutable(kw_only=True)
class ProcessorBackendPluginSharedState(Generic[ProcessorConfigT, MetadataT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ProcessorConfigT = attrs.field()
    replaying: bool = attrs.field(default=False)
    metadata: Optional[MetadataT] = attrs.field(default=None)

    @property
    def ready(self) -> bool:
        try:
            self.session_config.validate()
            self.processor_config.validate(self.session_config)
        except a121.ValidationError:
            return False
        else:
            return True


class GenericProcessorBackendPluginBase(
    Generic[InputT, ProcessorConfigT, ResultT, MetadataT],
    A121BackendPluginBase[ProcessorBackendPluginSharedState[ProcessorConfigT, MetadataT]],
):
    _processor_instance: Optional[
        GenericProcessorBase[InputT, ProcessorConfigT, ResultT, MetadataT]
    ]
    _recorder: Optional[a121.H5Recorder]
    _started: bool

    PLUGIN_PRESETS: Mapping[int, Callable[[], ProcessorPluginPreset]] = {}

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ):
        super().__init__(callback=callback, generation=generation, key=key)
        self._processor_instance = None
        self._recorder = None
        self._log = BackendLogger.getLogger(__name__)
        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.session_config = a121.SessionConfig.from_json(file["session_config"][()])
        self.shared_state.processor_config = self.get_processor_config_cls().from_json(
            file["processor_config"][()]
        )

    @is_task
    @abc.abstractmethod
    def restore_defaults(self) -> None:
        pass

    def _sync_sensor_ids(self) -> None:
        if self.client is not None:
            sensor_ids = self.client.server_info.connected_sensors

            if (
                len(sensor_ids) > 0
                and self.shared_state.session_config.sensor_id not in sensor_ids
            ):
                self.shared_state.session_config.sensor_id = sensor_ids[0]

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(
            file, "session_config", self.shared_state.session_config.to_json()
        )
        _create_h5_string_dataset(
            file, "processor_config", self.shared_state.processor_config.to_json()
        )

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        self.shared_state.session_config = record.session_config
        algo_group = record.get_algo_group(self.key)  # noqa: F841
        self.shared_state.processor_config = self.get_processor_config_cls().from_json(
            algo_group["processor_config"][()]
        )

    @is_task
    def update_session_config(self, *, session_config: a121.SessionConfig) -> None:
        self.shared_state.session_config = session_config
        self.broadcast()

    @is_task
    def update_processor_config(self, *, processor_config: ProcessorConfigT) -> None:
        self.shared_state.processor_config = processor_config
        self.broadcast()

    def _validate_session_config(self, session_config: a121.SessionConfig) -> None:
        """Hook for validating session configs."""
        pass

    def _start_session(self, recorder: Optional[a121.H5Recorder]) -> None:
        session_config = self.shared_state.session_config
        self._validate_session_config(session_config)

        if recorder:
            algo_group = recorder.require_algo_group(self.key)  # noqa: F841

            # TODO: break out saving (?)
            _create_h5_string_dataset(
                algo_group, "processor_config", self.shared_state.processor_config.to_json()
            )
        assert self.client
        metadata = self.client.setup_session(session_config)
        the_first_sensor_config = next(
            _core.utils.iterate_extended_structure_values(session_config.groups)
        )
        self._processor_instance = self.get_processor_cls()(
            sensor_config=the_first_sensor_config,  # FIXME: a bit scuffed but wth
            metadata=metadata,  # type: ignore[arg-type]
            processor_config=self.shared_state.processor_config,
        )

        self.shared_state.metadata = metadata  # type: ignore[assignment]
        self.client.start_session(self._recorder)

        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(metadata=metadata, sensor_config=the_first_sensor_config),
                recipient="plot_plugin",
            )
        )

    def end_session(self) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")
        self.client.stop_session()

    @classmethod
    @abc.abstractmethod
    def get_processor_cls(
        cls,
    ) -> Type[GenericProcessorBase[InputT, ProcessorConfigT, ResultT, MetadataT]]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfigT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        pass

    @staticmethod
    def _format_warning(s: str) -> str:
        return f'<p style="color: #FD5200;"><b>Warning: {s}</b></p>'


class ProcessorBackendPluginBase(
    GenericProcessorBackendPluginBase[a121.Result, ProcessorConfigT, ResultT, a121.Metadata]
):
    def _validate_session_config(self, session_config: a121.SessionConfig) -> None:
        if session_config.extended:
            raise ValueError("Extended session configs are not supported.")

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = ProcessorBackendPluginSharedState(
            session_config=a121.SessionConfig(self.get_default_sensor_config()),
            processor_config=self.get_processor_config_cls()(),
        )

        self.broadcast(sync=True)

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        processor_preset = preset_config()
        self.shared_state.session_config = processor_preset.session_config
        self.shared_state.processor_config = processor_preset.processor_config
        self.broadcast(sync=True)

    def get_next(self) -> None:
        if self._processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")

        assert self.client
        result = self.client.get_next()
        assert isinstance(result, a121.Result)  # TODO: fix

        self._frame_count += 1

        if result.data_saturated:
            self.send_status_message(self._format_warning(DATA_SATURATED_MESSAGE))

        if result.calibration_needed:
            self.send_status_message(self._format_warning(CALIBRATION_NEEDED_MESSAGE))

        if result.frame_delayed:
            self.send_status_message(self._format_warning(FRAME_DELAYED_MESSAGE))

        processor_result = self._processor_instance.process(result)
        self.callback(GeneralMessage(name="rate_stats", data=self.client._rate_stats))
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))
        self.callback(GeneralMessage(name="plot", data=processor_result, recipient="plot_plugin"))
