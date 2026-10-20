# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs

from PySide6.QtWidgets import QPushButton, QTabWidget, QVBoxLayout

from acconeer.exptool import a2
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.a2._core.entities.configs import sensor_config
from acconeer.exptool.app.new.ui.components.attrs_config_editor import AttrsConfigEditor
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.pidgets import pidgets

from .subsweep_config_editor import SubsweepConfigEditor


class _SensorConfigParametersEditor(AttrsConfigEditor[a2.SensorConfig]):
    """This is a "partial editor" that only modifies some fields."""

    IDLE_STATE_LABEL_MAP = {
        a2.IdleState.ARMED: "Armed",
        a2.IdleState.READY: "Ready",
    }

    def __init__(self, save_load_buttons: bool) -> None:
        super().__init__(
            title="Sensor parameters",
            config_type=a2.SensorConfig,
            save_load_buttons=save_load_buttons,
            factory_mapping={
                "sweeps_per_frame": pidgets.IntPidgetFactory(
                    name_label_text="Sweeps per frame:",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SensorConfig, "sweeps_per_frame"
                    ),
                    limits=(
                        sensor_config.MIN_SWEEPS_PER_FRAME,
                        sensor_config.MAX_SWEEPS_PER_FRAME,
                    ),
                ),
                "sweep_rate": pidgets.OptionalFloatPidgetFactory(
                    name_label_text="Sweep rate:",
                    name_label_tooltip=get_attribute_docstring(a2.SensorConfig, "sweep_rate"),
                    limits=(1, 1e6),
                    decimals=0,
                    init_set_value=1000.0,
                    placeholder_text="- Hz",
                    suffix="Hz",
                    checkbox_label_text="Limit",
                ),
                "frame_rate": pidgets.OptionalFloatPidgetFactory(
                    name_label_text="Frame rate:",
                    name_label_tooltip=get_attribute_docstring(a2.SensorConfig, "frame_rate"),
                    limits=(0.01, 1e6),
                    decimals=2,
                    init_set_value=10.0,
                    placeholder_text="- Hz",
                    suffix="Hz",
                    checkbox_label_text="Limit",
                ),
                "inter_sweep_idle_state": pidgets.EnumPidgetFactory(
                    enum_type=a2.IdleState,
                    name_label_text="Inter sweep idle state:",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SensorConfig,
                        "inter_sweep_idle_state",
                    ),
                    label_mapping=self.IDLE_STATE_LABEL_MAP,
                ),
                "inter_frame_idle_state": pidgets.EnumPidgetFactory(
                    enum_type=a2.IdleState,
                    name_label_text="Inter frame idle state:",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SensorConfig,
                        "inter_frame_idle_state",
                    ),
                    label_mapping=self.IDLE_STATE_LABEL_MAP,
                ),
                "jitter_compensation": pidgets.CheckboxPidgetFactory(
                    name_label_text="Jitter compensation",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SensorConfig, "jitter_compensation"
                    ),
                ),
            },
        )


class SensorConfigEditor(DataEditor[t.Optional[a2.SensorConfig]]):
    _TAB_LABEL_FMT = "{}    "
    _TMP_LABEL = ""

    def __init__(self, save_load_buttons: bool = True, single_subsweep: bool = False) -> None:
        super().__init__()

        self._sensor_param_editor = _SensorConfigParametersEditor(save_load_buttons)
        self._sensor_param_editor.sig_update.connect(self._emit_current_data)

        self._add_subsweep_button = QPushButton("+")
        self._add_subsweep_button.setFlat(True)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setDocumentMode(True)
        self._tabs.setCornerWidget(self._add_subsweep_button)
        self._add_subsweep_button.setHidden(single_subsweep)

        self._add_subsweep_button.clicked.connect(
            lambda: self.set_data(self._append_subsweep(self.get_data(), a2.SubsweepConfig()))
        )
        self._add_subsweep_button.clicked.connect(self._emit_current_data)

        self._tabs.tabCloseRequested.connect(
            lambda idx: self.set_data(self._remove_subsweep_at_index(self.get_data(), idx))
        )
        self._tabs.tabCloseRequested.connect(self._emit_current_data)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._sensor_param_editor)
        layout.addWidget(self._tabs)

        self.setLayout(layout)

    @staticmethod
    def _append_subsweep(
        sensor_config: t.Optional[a2.SensorConfig], subsweep_config: a2.SubsweepConfig
    ) -> a2.SensorConfig:
        if sensor_config is None:
            raise RuntimeError

        new_subsweeps = sensor_config.subsweeps + [subsweep_config]
        return attrs.evolve(sensor_config, subsweeps=new_subsweeps)

    @staticmethod
    def _remove_subsweep_at_index(
        sensor_config: t.Optional[a2.SensorConfig], subsweep_index: int
    ) -> a2.SensorConfig:
        if sensor_config is None:
            raise RuntimeError

        new_subsweeps = [
            subsweep_config
            for (i, subsweep_config) in enumerate(sensor_config.subsweeps)
            if i != subsweep_index
        ]
        return attrs.evolve(sensor_config, subsweeps=new_subsweeps)

    def _emit_current_data(self) -> None:
        self.sig_update.emit(self.get_data())

    def set_data(self, data: t.Optional[a2.SensorConfig]) -> None:
        self.setDisabled(data is None)

        if data is None:
            return

        self._sensor_param_editor.set_data(data)

        old_index = self._tabs.currentIndex()

        self._require_n_tabs(data.num_subsweeps, data.jitter_compensation)

        for config, editor in zip(data.subsweeps, self._subsweep_config_editors):
            editor.set_data(config)

        self._tabs.setCurrentIndex(old_index if old_index < self._tabs.count() else 0)

    def _require_n_tabs(self, n: int, jitter_compensation: bool) -> None:
        while self._tabs.count() < n:
            new_editor = SubsweepConfigEditor()
            new_editor.sig_update.connect(self._emit_current_data)

            self._tabs.addTab(new_editor, self._TMP_LABEL)

        while self._tabs.count() > n:
            self._tabs.removeTab(0)

        self._tabs.setTabsClosable(self._tabs.count() > 1)
        # RSS spends one slot on the loopback subsweep of the jitter compensation
        max_num_subsweeps = a2.SensorConfig.MAX_NUM_SUBSWEEPS - int(jitter_compensation)
        self._add_subsweep_button.setEnabled(self._tabs.count() < max_num_subsweeps)

        for i in range(self._tabs.count()):
            self._tabs.setTabText(i, self._TAB_LABEL_FMT.format(i + 1))

    def get_data(self) -> t.Optional[a2.SensorConfig]:
        partial_sensor_config = self._sensor_param_editor.get_data()

        assert partial_sensor_config is not None

        subsweep_configs = []
        for editor in self._subsweep_config_editors:
            assert (subsweep_config := editor.get_data()) is not None
            subsweep_configs.append(subsweep_config)

        return a2.SensorConfig(
            subsweeps=subsweep_configs,
            frame_rate=partial_sensor_config.frame_rate,
            sweeps_per_frame=partial_sensor_config.sweeps_per_frame,
            sweep_rate=partial_sensor_config.sweep_rate,
            inter_frame_idle_state=partial_sensor_config.inter_frame_idle_state,
            inter_sweep_idle_state=partial_sensor_config.inter_sweep_idle_state,
            jitter_compensation=partial_sensor_config.jitter_compensation,
        )

    @property
    def _subsweep_config_editors(self) -> list[SubsweepConfigEditor]:
        tab_widgets = [self._tabs.widget(tab_idx) for tab_idx in range(self._tabs.count())]

        assert all(isinstance(widget, SubsweepConfigEditor) for widget in tab_widgets)

        return t.cast(t.List[SubsweepConfigEditor], tab_widgets)

    @property
    def is_ready(self) -> bool:
        return self._sensor_param_editor.is_ready and all(
            editor.is_ready for editor in self._subsweep_config_editors
        )

    def handle_validation_results(self, results: list[ValidationResult]) -> list[ValidationResult]:
        not_handled = self._sensor_param_editor.handle_validation_results(results)
        for subsweep_editor in self._subsweep_config_editors:
            not_handled = subsweep_editor.handle_validation_results(not_handled)
        return not_handled
