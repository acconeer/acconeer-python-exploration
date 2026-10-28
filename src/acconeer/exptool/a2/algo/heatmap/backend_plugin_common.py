# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t
from enum import Enum, auto

import attrs
import h5py
import numpy as np
import numpy.typing as npt
import typing_extensions as te

from acconeer.exptool import a2
from acconeer.exptool import type_migration as tm
from acconeer.exptool._core.class_creation.enum import find_by_name
from acconeer.exptool._core.class_creation.mixins import AttrsMappingTransformsMixin
from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.a2._core.entities import Metadata
from acconeer.exptool.a2.algo._plugins import A2BackendPluginBase
from acconeer.exptool.a2.algo._utils import HEATMAP_FALLBACK_UPDATE_RATE, estimate_max_update_rate
from acconeer.exptool.a2.algo.heatmap.config_common import HeatmapConfigCommon
from acconeer.exptool.a2.algo.heatmap.plot_config_common import HeatmapPlotConfig
from acconeer.exptool.a2.algo.heatmap.processor_common import (
    HeatmapProcessorCommon,
)
from acconeer.exptool.a2.algo.noise_normalization import (
    NoiseNormalizationRecording,
    NoiseNormalizationResultProcessor,
    load_noise_normalization_recording,
    save_noise_normalization_recording,
)
from acconeer.exptool.app.new import (
    HandledException,
    Message,
    PluginGeneration,
    backend,
    is_task,
)


class PluginPresetId(Enum):
    DEFAULT = auto()


_HeatmapConfigT = t.TypeVar("_HeatmapConfigT", bound=HeatmapConfigCommon)
_PlotConfigT = t.TypeVar("_PlotConfigT", bound=HeatmapPlotConfig)


@attrs.mutable
class HeatmapPlotOrientation(AttrsMappingTransformsMixin):
    rotation: int = attrs.field(default=0)
    inv_x: bool = attrs.field(default=False)
    inv_y: bool = attrs.field(default=False)


class TabState(Enum):
    HEATMAP_POLAR = auto()
    HEATMAP_CARTESIAN = auto()
    ANGULAR = auto()

    @classmethod
    def _missing_(cls, value: object) -> te.Self | None:
        if isinstance(value, str):
            return find_by_name(cls, value)
        else:
            return None


@attrs.mutable
class SharedState(t.Generic[_HeatmapConfigT, _PlotConfigT]):
    session_config: a2.SessionConfig
    heatmap_config: _HeatmapConfigT
    metadata: Metadata | None
    noise_normalization_recording: NoiseNormalizationRecording | None
    heatmap_plot_orientation: HeatmapPlotOrientation
    max_update_rate: float | None
    tab_state: TabState
    replaying_record: bool
    plot_config: _PlotConfigT

    def _collect_validation_results(self) -> list[ValidationResult]:
        return [
            *self.heatmap_config._collect_validation_results(self.session_config),
            *self.session_config._collect_validation_results(),
        ]


class BackendPlugin(
    A2BackendPluginBase[SharedState[_HeatmapConfigT, _PlotConfigT]],
    t.Generic[_HeatmapConfigT, _PlotConfigT],
):
    def __init__(
        self,
        callback: t.Callable[[Message], None],
        generation: PluginGeneration,
        key: str,
        heatmap_config_dataset_name: str,
        algo_group_name: str,
        heatmap_config_class: type[_HeatmapConfigT],
        heatmap_config_timeline: tm.Node[_HeatmapConfigT, te.Never, t.Any],
        heatmap_processor_class: type[HeatmapProcessorCommon[_HeatmapConfigT]],
        plot_config_class: type[_PlotConfigT],
    ) -> None:
        super().__init__(callback, generation, key)
        self.plot_config_class = plot_config_class
        self.shared_state = SharedState(
            session_config=a2.SessionConfig.default(),
            heatmap_config=heatmap_config_class.default(),
            metadata=None,
            noise_normalization_recording=None,
            heatmap_plot_orientation=HeatmapPlotOrientation(),
            max_update_rate=None,
            tab_state=TabState.HEATMAP_CARTESIAN,
            replaying_record=False,
            plot_config=plot_config_class.default(),
        )
        self.processor: HeatmapProcessorCommon[_HeatmapConfigT] | None = None
        self.noise_normalization_processor: NoiseNormalizationResultProcessor | None = None
        self.steering_vector_cache: dict[tuple[int, int], npt.NDArray[np.complex128]] = {}
        self.algo_group_name = algo_group_name
        self.heatmap_config_dataset_name = heatmap_config_dataset_name
        self.heatmap_processor_class = heatmap_processor_class
        self.heatmap_config_timeline = heatmap_config_timeline
        self.heatmap_config_class = heatmap_config_class
        self.broadcast()

    def _start_session(self, recorder: a2.H5Recorder | None) -> None:
        assert self.client is not None
        if (
            self.shared_state.noise_normalization_recording is None
            or self.shared_state.session_config
            != self.shared_state.noise_normalization_recording.noise_config
        ) and not self.shared_state.replaying_record:
            self.shared_state.noise_normalization_recording = self.record_noise()

            # If the noise normalization is mismatched, the max update rate will also be wrong
            max_update_rate = estimate_max_update_rate(
                self.client, self.shared_state.session_config
            )
            self.shared_state.max_update_rate = max_update_rate

        self.shared_state.replaying_record = False

        if self.shared_state.max_update_rate is None:
            max_update_rate = HEATMAP_FALLBACK_UPDATE_RATE
        else:
            max_update_rate = self.shared_state.max_update_rate

        if self.shared_state.session_config.update_rate is None:
            update_rate = max_update_rate
        else:
            update_rate = min(
                max_update_rate,
                self.shared_state.session_config.update_rate,
            )

        if recorder:
            self.client.attach_recorder(recorder)
            algo_group = recorder.require_algo_group(self.algo_group_name)
            algo_group.create_dataset(
                self.heatmap_config_dataset_name, data=self.shared_state.heatmap_config.to_json()
            )
            algo_group.create_dataset("max_update_rate", data=max_update_rate)
            save_noise_normalization_recording(
                algo_group, self.shared_state.noise_normalization_recording
            )

        self.shared_state.metadata = self.client.setup_session(self.shared_state.session_config)

        if self.shared_state.noise_normalization_recording is not None:
            self.noise_normalization_processor = NoiseNormalizationResultProcessor(
                self.shared_state.session_config,
                self.shared_state.noise_normalization_recording,
            )
        else:
            self.noise_normalization_processor = None

        if (
            len(self.shared_state.session_config.sensor_configs) == 1
            and self.shared_state.session_config.sensor_config.num_subsweeps == 1
        ):
            subsweep = self.shared_state.session_config.sensor_config.subsweep
            extra_processor_kwargs: dict[str, t.Any] = {}
            display_mode = getattr(self.shared_state.plot_config, "display_mode", None)
            if display_mode is not None:
                extra_processor_kwargs["display_mode"] = display_mode
            self.processor = self.heatmap_processor_class(
                subsweep, self.shared_state.heatmap_config, update_rate, **extra_processor_kwargs
            )

        self.client.start_session()
        self.broadcast()

    def get_next(self) -> None:
        assert self.client is not None

        group_result = self.client.get_next(format=a2.Client.ResultFormat.FULL)

        if self.noise_normalization_processor is not None:
            group_result = self.noise_normalization_processor.process(group_result)

        if self.processor is None:
            self.callback(backend.PlotMessage(result=(group_result, None)))
        else:
            proc_result = self.processor.process(group_result.result)
            self.callback(backend.PlotMessage(result=(group_result, proc_result)))

    def end_session(self) -> None:
        assert self.client is not None

        self.client.stop_session()

    def record_noise(self) -> NoiseNormalizationRecording:
        assert self.client is not None
        try:
            noise_normalization_recording = NoiseNormalizationRecording.create(
                self.client, self.shared_state.session_config
            )
        except Exception as exc:
            msg = "Failed to record noise for normalization"
            raise HandledException(msg) from exc
        return noise_normalization_recording

    @is_task
    def update_session_config(self, session_config: a2.SessionConfig) -> None:
        self.shared_state.session_config = session_config
        self.broadcast()

    @is_task
    def update_heatmap_config(self, heatmap_config: _HeatmapConfigT) -> None:
        self.shared_state.heatmap_config = heatmap_config
        self.broadcast()

    @is_task
    def update_plot_config(self, plot_config: _PlotConfigT) -> None:
        self.shared_state.plot_config = plot_config
        self.broadcast()

    @is_task
    def update_tab_display(self, tab: TabState) -> None:
        self.shared_state.tab_state = tab
        self.broadcast()

    @is_task
    def heatmap_plot_rotate(self) -> None:
        self.shared_state.heatmap_plot_orientation.rotation += 90
        self.shared_state.heatmap_plot_orientation.rotation %= 360
        self.broadcast()

    @is_task
    def heatmap_plot_invert_x(self) -> None:
        x_inverted = self.shared_state.heatmap_plot_orientation.inv_x
        self.shared_state.heatmap_plot_orientation.inv_x = not x_inverted
        self.broadcast()

    @is_task
    def heatmap_plot_invert_y(self) -> None:
        y_inverted = self.shared_state.heatmap_plot_orientation.inv_y
        self.shared_state.heatmap_plot_orientation.inv_y = not y_inverted
        self.broadcast()

    @is_task
    def heatmap_plot_reset(self) -> None:
        self.shared_state.heatmap_plot_orientation = HeatmapPlotOrientation()
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        if preset_id == PluginPresetId.DEFAULT.value:
            self.update_session_config(a2.SessionConfig.default())
            self.update_heatmap_config(self.heatmap_config_class.default())
            self.update_plot_config(self.plot_config_class.default())
            self.broadcast()
        else:
            msg = f"Unknown preset id {preset_id}"
            raise RuntimeError(msg)

    def load_from_record_setup(
        self,
        *,
        record: a2.H5Record,
        config_override: t.Any | None = None,
        context_override: t.Any | None = None,
    ) -> None:
        if context_override is not None:
            self._logger.warning(f"Ignoring context override of type: {type(context_override)}")

        self.update_session_config(record.session_config)

        try:
            algo_group = record.file["algo"]
            noise_normalization_recording = load_noise_normalization_recording(algo_group)
        except Exception:
            msg = "No noise normalization recording loaded."
            self.callback(backend.StatusMessage(status=msg))
            noise_normalization_recording = None
        finally:
            self.shared_state.replaying_record = True
            self.shared_state.noise_normalization_recording = noise_normalization_recording

        try:
            dataset = algo_group.get("max_update_rate")
            max_update_rate = float(dataset[()])
        except Exception:
            msg = "No max_update_rate loaded."
            self.callback(backend.StatusMessage(status=msg))
            max_update_rate = None
        finally:
            self.shared_state.max_update_rate = max_update_rate

        try:
            if config_override is None:
                algo_group = record.file["algo"]
                config_data = algo_group[self.heatmap_config_dataset_name][()]
                config = self.heatmap_config_timeline.migrate(bytes.decode(config_data))
            elif isinstance(config_override, self.heatmap_config_class):
                config = config_override
            else:
                msg = f"'config_override' was of incorrect type {type(config_override)}. Expected {self.heatmap_config_class}"
                raise TypeError(msg)
        except Exception:
            msg = "Could not load heatmap config, falling back to default"
            self.callback(backend.StatusMessage(status=msg))
            config = self.heatmap_config_class.default()
        finally:
            self.update_heatmap_config(config)

    def _load_from_cache(self, file: h5py.File) -> SharedState[_HeatmapConfigT, _PlotConfigT]:
        cached: dict[str, t.Any] = {}
        if dataset := file.get("session_config"):
            cached["session_config"] = a2.SessionConfig.from_json(bytes.decode(dataset[()]))

        if dataset := file.get(self.heatmap_config_dataset_name):
            cached["heatmap_config"] = self.heatmap_config_timeline.migrate(
                bytes.decode(dataset[()])
            )

        if noise_group := file.get("noise_group"):
            try:
                cached["noise_normalization_recording"] = load_noise_normalization_recording(
                    noise_group
                )
            except tm.MigrationError:
                self._logger.warning("Could not load noise normalization recording from cache")

        if dataset := file.get("heatmap_plot_orientation"):
            cached["heatmap_plot_orientation"] = HeatmapPlotOrientation.from_json(
                bytes.decode(dataset[()])
            )

        if dataset := file.get("max_update_rate"):
            cached["max_update_rate"] = float(dataset[()])

        if dataset := file.get("plot_config"):
            cached["plot_config"] = self.plot_config_class.from_json(bytes.decode(dataset[()]))

        return attrs.evolve(self.shared_state, **cached)

    def save_to_cache(self, file: h5py.File) -> None:
        file.create_dataset("session_config", data=self.shared_state.session_config.to_json())
        file.create_dataset(
            self.heatmap_config_dataset_name, data=self.shared_state.heatmap_config.to_json()
        )
        noise_group = file.create_group("noise_group")
        save_noise_normalization_recording(
            noise_group, self.shared_state.noise_normalization_recording
        )
        if self.shared_state.max_update_rate is not None:
            file.create_dataset("max_update_rate", data=self.shared_state.max_update_rate)
        file.create_dataset(
            "heatmap_plot_orientation",
            data=self.shared_state.heatmap_plot_orientation.to_json(),
        )
        file.create_dataset("plot_config", data=self.shared_state.plot_config.to_json())
