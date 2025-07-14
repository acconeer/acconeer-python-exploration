# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import abc
import itertools
from typing import Callable, Dict, Generic, List, Mapping, Optional, Type, Union

import attrs
import h5py

from acconeer.exptool import a121
from acconeer.exptool.a121._core import utils as core_utils
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
    PluginGeneration,
)
from acconeer.exptool.app.new.backend import (
    BackendLogger,
    GeneralMessage,
    Message,
    PlotMessage,
    RecipientLiteral,
    StatusMessage,
    is_task,
)


@attrs.mutable(kw_only=True)
class ProcessorPluginPreset(Generic[ProcessorConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ProcessorConfigT = attrs.field()


@attrs.mutable(kw_only=True)
class ProcessorBackendPluginSharedState(Generic[ProcessorConfigT]):
    session_config: a121.SessionConfig = attrs.field()
    processor_config: ProcessorConfigT = attrs.field()
    replaying: bool = attrs.field(default=False)
    metadata: Union[a121.Metadata, list[dict[int, a121.Metadata]], None] = attrs.field(
        default=None
    )

    @property
    def ready(self) -> bool:
        try:
            self.session_config.validate()
            self.processor_config.validate(self.session_config)
        except a121.ValidationError:
            return False
        else:
            return True


@attrs.frozen(kw_only=True)
class SetupMessage(GeneralMessage, Generic[ProcessorConfigT]):
    session_config: a121.SessionConfig
    processor_config: ProcessorConfigT
    metadata: Union[a121.Metadata, list[dict[int, a121.Metadata]]]
    name: str = attrs.field(default="setup", init=False)
    recipient: RecipientLiteral = attrs.field(default="plot_plugin", init=False)


class GenericProcessorBackendPluginBase(
    Generic[InputT, ProcessorConfigT, ResultT, MetadataT],
    A121BackendPluginBase[ProcessorBackendPluginSharedState[ProcessorConfigT]],
):
    _processor_instance: Optional[GenericProcessorBase[InputT, ResultT]]
    _started: bool

    PLUGIN_PRESETS: Mapping[int, Callable[[], ProcessorPluginPreset[ProcessorConfigT]]] = {}

    def __init__(
        self, callback: Callable[[Message], None], generation: PluginGeneration, key: str
    ):
        super().__init__(callback=callback, generation=generation, key=key)
        self._processor_instance = None
        self._log: BackendLogger = BackendLogger.getLogger(__name__)
        self.restore_defaults()

    def _load_from_cache(self, file: h5py.File) -> None:
        self.shared_state.session_config = a121.SessionConfig.from_json(file["session_config"][()])
        self.shared_state.processor_config = self.get_processor_config_cls().from_json(
            file["processor_config"][()]
        )

    def _sync_sensor_ids(self) -> None:
        if self.client is None:
            return

        available_sensor_ids = self.client.server_info.connected_sensors

        if len(available_sensor_ids) == 0:
            return

        original_session_config = self.shared_state.session_config

        adjusted_groups = core_utils.create_extended_structure(
            (
                group_idx,
                sensor_id
                if (sensor_id in available_sensor_ids)
                else next(fallback_sensor_ids_iter),
                sensor_config,
            )
            for (group_idx, sensor_id, sensor_config), fallback_sensor_ids_iter in zip(
                core_utils.iterate_extended_structure(original_session_config.groups),
                itertools.tee(available_sensor_ids, len(available_sensor_ids)),
            )
        )
        self.shared_state.session_config = a121.SessionConfig(
            adjusted_groups,
            update_rate=original_session_config.update_rate,
            extended=original_session_config.extended,
        )

    def save_to_cache(self, file: h5py.File) -> None:
        _create_h5_string_dataset(
            file, "session_config", self.shared_state.session_config.to_json()
        )
        _create_h5_string_dataset(
            file, "processor_config", self.shared_state.processor_config.to_json()
        )

    def load_from_record_setup(self, *, record: a121.H5Record) -> None:
        self.shared_state.session_config = record.session_config
        try:
            algo_group = record.get_algo_group(self.key)  # noqa: F841
        except KeyError:
            self.shared_state.processor_config = self.get_processor_config_cls()()
            self.callback(
                StatusMessage(
                    status="Could not load algo group. "
                    + "Falling back to default processor config"
                )
            )
        else:
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

        assert self.client
        if recorder:
            algo_group = recorder.require_algo_group(self.key)  # noqa: F841

            # TODO: break out saving (?)
            _create_h5_string_dataset(
                algo_group, "processor_config", self.shared_state.processor_config.to_json()
            )

            self.client.attach_recorder(recorder)

        metadata = self.client.setup_session(session_config)
        self.shared_state.metadata = metadata

        self._processor_instance = self.get_processor(self.shared_state)

        self.client.start_session()

        self.callback(
            SetupMessage(
                metadata=metadata,
                session_config=session_config,
                processor_config=self.shared_state.processor_config,
            )
        )

    def end_session(self) -> None:
        if self.client is None:
            msg = "Client is not attached. Can not 'stop'."
            raise RuntimeError(msg)

        self.client.stop_session()

        recorder = self.client.detach_recorder()
        if recorder is not None:
            recorder.close()

    @classmethod
    @abc.abstractmethod
    def get_processor(
        cls, state: ProcessorBackendPluginSharedState[ProcessorConfigT]
    ) -> GenericProcessorBase[InputT, ResultT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_processor_config_cls(cls) -> Type[ProcessorConfigT]:
        pass

    @classmethod
    @abc.abstractmethod
    def get_default_sensor_config(cls) -> a121.SensorConfig:
        pass


class ProcessorBackendPluginBase(
    GenericProcessorBackendPluginBase[a121.Result, ProcessorConfigT, ResultT, a121.Metadata]
):
    def _validate_session_config(self, session_config: a121.SessionConfig) -> None:
        if session_config.extended:
            msg = "Extended session configs are not supported."
            raise ValueError(msg)

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = ProcessorBackendPluginSharedState(
            session_config=a121.SessionConfig(self.get_default_sensor_config()),
            processor_config=self.get_processor_config_cls()(),
        )

        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        processor_preset = preset_config()
        self.shared_state.session_config = processor_preset.session_config
        self.shared_state.processor_config = processor_preset.processor_config
        self.broadcast()

    def get_next(self) -> None:
        if self._processor_instance is None:
            msg = "Processor is None. 'start' needs to be called before 'get_next'"
            raise RuntimeError(msg)

        assert self.client
        result = self.client.get_next()
        assert isinstance(result, a121.Result)  # TODO: fix

        processor_result = self._processor_instance.process(result)

        self.callback(PlotMessage(result=processor_result))


class ExtendedProcessorBackendPluginBase(
    GenericProcessorBackendPluginBase[
        List[Dict[int, a121.Result]], ProcessorConfigT, ResultT, List[Dict[int, a121.Metadata]]
    ]
):
    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = ProcessorBackendPluginSharedState(
            session_config=a121.SessionConfig(self.get_default_sensor_config()),
            processor_config=self.get_processor_config_cls()(),
        )

        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        preset_config = self.PLUGIN_PRESETS[preset_id]
        processor_preset = preset_config()
        self.shared_state.session_config = processor_preset.session_config
        self.shared_state.processor_config = processor_preset.processor_config
        self.broadcast()

    def get_next(self) -> None:
        if self._processor_instance is None:
            msg = "Processor is None. 'start' needs to be called before 'get_next'"
            raise RuntimeError(msg)

        assert self.client
        result = self.client.get_next()
        if isinstance(result, a121.Result):
            results = [{self.client.session_config.sensor_id: result}]
        else:
            results = result

        processor_result = self._processor_instance.process(results)

        self.callback(PlotMessage(result=processor_result))
