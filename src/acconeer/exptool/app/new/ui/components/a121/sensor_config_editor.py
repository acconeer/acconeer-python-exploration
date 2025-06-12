# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import logging
from functools import partial
from typing import Any, Iterator, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QToolButton, QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.app.new.ui.components import pidgets
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.group_box import GroupBox
from acconeer.exptool.app.new.ui.components.json_save_load_buttons import (
    JsonButtonOperations,
    create_json_save_load_buttons_from_type,
)
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping

from .subsweep_config_editor import SubsweepConfigEditor


log = logging.getLogger(__name__)


class SensorConfigEditor(DataEditor[Optional[a121.SensorConfig]]):
    sig_update = Signal(object)

    _sensor_config: Optional[a121.SensorConfig]

    _sensor_config_pidgets: dict[str, pidgets.Pidget]
    _erroneous_aspects: set[str]
    _read_only: bool
    _supports_multiple_subsweeps: bool

    SPACING = 15
    IDLE_STATE_LABEL_MAP = {
        a121.IdleState.READY: "Ready",
        a121.IdleState.SLEEP: "Sleep",
        a121.IdleState.DEEP_SLEEP: "Deep sleep",
    }
    SENSOR_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "sweeps_per_frame": pidgets.IntPidgetFactory(
            name_label_text="Sweeps per frame:",
            name_label_tooltip=(
                "The number of sweeps that will be captured in each frame (measurement)."
            ),
            limits=(1, 4095),
        ),
        "sweep_rate": pidgets.OptionalFloatPidgetFactory(
            name_label_text="Sweep rate:",
            name_label_tooltip=(
                "The sweep rate for sweeps in a frame (measurement).\n"
                "If 'Limit' is unchecked, the sweep rate will be as fast as possible."
            ),
            limits=(1, 1e6),
            decimals=0,
            init_set_value=1000.0,
            placeholder_text="- Hz",
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "frame_rate": pidgets.OptionalFloatPidgetFactory(
            name_label_text="Frame rate:",
            name_label_tooltip=(
                "Frame rate.\nIf 'Limit' is unchecked, the rate is not limited by the sensor "
                "but by the rate that the server acknowledge and reads out the frame."
            ),
            limits=(0.1, 1e4),
            decimals=1,
            init_set_value=10.0,
            placeholder_text="- Hz",
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "inter_sweep_idle_state": pidgets.EnumPidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter sweep idle state:",
            name_label_tooltip=(
                "The inter sweep idle state is the state the sensor idles in "
                "between each sweep in a frame."
            ),
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "inter_frame_idle_state": pidgets.EnumPidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter frame idle state:",
            name_label_tooltip=(
                "The inter frame idle state is the state the sensor idles in between each frame."
            ),
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "continuous_sweep_mode": pidgets.CheckboxPidgetFactory(
            name_label_text="Continuous sweep mode",
            name_label_tooltip=(
                "<p>With CSM, the sensor timing is set up to generate a continuous "
                "stream of sweeps, even if more than one sweep per frame is used. "
                "The interval between the last sweep in one frame to the first "
                "sweep in the next frame becomes equal to the interval between "
                "sweeps within a frame (given by the sweep rate).</p>"
                ""
                "<p>It ensures that:</p>"
                ""
                "<p>'frame rate' = 'sweep rate' / 'sweeps per frame'</p>"
                ""
                "While the frame rate parameter can be set to approximately "
                "satisfy this condition, using CSM is more precise."
                ""
                "<p>If only one sweep per frame is used, CSM has no use since a "
                "continuous stream of sweeps is already given (if a fixed frame "
                "rate is used).</p>"
                ""
                "<p>The main use for CSM is to allow reading out data at a slower "
                "rate than the sweep rate, while maintaining that sweep rate "
                "continuously.</p>"
                ""
                "<p>Note that in most cases, double buffering must be enabled to "
                "allow high rates without delays.</p>"
            ),
        ),
        "double_buffering": pidgets.CheckboxPidgetFactory(
            name_label_text="Double buffering",
            name_label_tooltip=(
                "Double buffering will split the sensor buffer in two halves. "
                "One half is used to read out the frame while sampling is done "
                "in the other half."
            ),
        ),
    }

    def __init__(
        self,
        supports_multiple_subsweeps: bool = False,
        json_button_operations: JsonButtonOperations = JsonButtonOperations(0),
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._sensor_config_pidgets = {}
        self._erroneous_aspects = set()

        self._sensor_config = None

        self._read_only = False
        self._supports_multiple_subsweeps = supports_multiple_subsweeps

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.sensor_group_box = GroupBox.vertical(
            "Sensor parameters",
            right_header=create_json_save_load_buttons_from_type(
                self,
                a121.SensorConfig,
                operations=json_button_operations,
            ),
            parent=self,
        )
        self.sensor_group_box.layout().setSpacing(self.SPACING)
        layout.addWidget(self.sensor_group_box)

        for aspect, factory in self.SENSOR_CONFIG_FACTORIES.items():
            pidget = factory.create(self.sensor_group_box)
            self.sensor_group_box.layout().addWidget(pidget)

            pidget.sig_update.connect(partial(self._update_sensor_config_aspect, aspect))

            self._sensor_config_pidgets[aspect] = pidget

        self.subsweep_group_box = GroupBox.vertical("Subsweep parameters", parent=self)
        self.subsweep_group_box.layout().setSpacing(self.SPACING)
        layout.addWidget(self.subsweep_group_box)

        self._tab_widget = QTabWidget(self)
        self._tab_widget.setStyleSheet("QTabWidget::pane { padding: 5px;}")
        self.subsweep_group_box.layout().addWidget(self._tab_widget)

        if supports_multiple_subsweeps:
            self._tab_widget.setTabsClosable(True)
            self._tab_widget.tabCloseRequested.connect(self._remove_subsweep_config)

            self._plus_button = QToolButton(self)
            self._plus_button.setText("+")
            layout.addWidget(self._plus_button)
            self._plus_button.clicked.connect(self._add_subsweep_config)
            self._tab_widget.setCornerWidget(self._plus_button)
            self._tab_widget.cornerWidget().setMinimumSize(self._plus_button.sizeHint())

        self.setLayout(layout)

    def set_read_only(self, read_only: bool) -> None:
        self._read_only = read_only

        for pidget in self._sensor_config_pidgets.values():
            pidget.setEnabled(not read_only)

        if self._supports_multiple_subsweeps:
            self._tab_widget.setTabsClosable(not read_only)
            self._plus_button.setEnabled(not read_only)

        for editor in self._subsweep_config_editors:
            editor.set_read_only(read_only)

    def set_data(self, sensor_config: Optional[a121.SensorConfig]) -> None:
        if self._sensor_config == sensor_config:
            return

        self._sensor_config = sensor_config

        self.setEnabled(sensor_config is not None)
        if self._sensor_config is None:
            log.debug("could not update ui as SensorConfig is None")
            return

        for aspect, pidget in self._sensor_config_pidgets.items():
            if aspect in self._erroneous_aspects:
                continue
            pidget.set_data(getattr(self._sensor_config, aspect))

        while self._tab_widget.count() > self._sensor_config.num_subsweeps:
            self._tab_widget.removeTab(0)

        while self._tab_widget.count() < self._sensor_config.num_subsweeps:
            new_tab_idx = self._tab_widget.count()
            self._tab_widget.addTab(self._create_subsweep_config_editor(new_tab_idx), "")

        for tab_idx, subsweep_editor in enumerate(self._subsweep_config_editors):
            self._tab_widget.setTabText(tab_idx, f"{tab_idx + 1}      ")
            subsweep_editor.sig_update.disconnect()
            subsweep_editor.sig_update.connect(
                partial(self._update_subsweep_config_at_index, tab_idx)
            )

        for subsweep, editor in zip(self._sensor_config.subsweeps, self._subsweep_config_editors):
            editor.set_data(subsweep)

    def get_data(self) -> Optional[a121.SensorConfig]:
        return copy.deepcopy(self._sensor_config)

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        for aspect, pidget in self._sensor_config_pidgets.items():
            if aspect not in self._erroneous_aspects:
                pidget.set_note_text("")

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        for subsweep_config_editor in self._subsweep_config_editors:
            unhandled_results = subsweep_config_editor.handle_validation_results(unhandled_results)

        return unhandled_results

    @property
    def is_ready(self) -> bool:
        return self._erroneous_aspects == set() and all(
            se.is_ready for se in self._subsweep_config_editors
        )

    def _handle_validation_result(self, result: a121.ValidationResult) -> bool:
        if result.aspect is None or self._sensor_config is None:
            return False

        if result.aspect in self._erroneous_aspects:
            # If there is an erroneous aspect in the GUI, we do not want to overwrite that.
            # Once the erroneous aspect is handled with, the same validation result will
            # come through here anyway
            return True

        result_handled = False

        if result.source == self._sensor_config:
            for aspect, pidget in self._sensor_config_pidgets.items():
                if result.aspect == aspect:
                    pidget.set_note_text(result.message, result.criticality)
                    result_handled = True

        return result_handled

    def _create_subsweep_config_editor(self, index: int) -> SubsweepConfigEditor:
        e = SubsweepConfigEditor()
        e.sig_update.connect(lambda ssc: self._update_subsweep_config_at_index(index, ssc))
        e.set_read_only(self._read_only)
        return e

    @property
    def _subsweep_config_editors(self) -> Iterator[SubsweepConfigEditor]:
        for tab_idx in range(self._tab_widget.count()):
            tab_widget = self._tab_widget.widget(tab_idx)
            assert isinstance(tab_widget, SubsweepConfigEditor)
            yield tab_widget

    def _add_subsweep_config(self) -> None:
        if self._sensor_config is None or self._sensor_config.num_subsweeps >= 4:
            return

        config = copy.deepcopy(self._sensor_config)
        config._subsweeps.append(a121.SubsweepConfig())
        self.set_data(config)
        self.sig_update.emit(config)

    def _remove_subsweep_config(self, idx: int) -> None:
        if self._sensor_config is None or len(self._sensor_config.subsweeps) <= 1:
            return

        config = copy.deepcopy(self._sensor_config)
        config._subsweeps.pop(idx)
        self.set_data(config)
        self.sig_update.emit(config)

    def _update_subsweep_config_at_index(
        self, index: int, subsweep_config: a121.SubsweepConfig
    ) -> None:
        if self._sensor_config is None or index not in range(self._sensor_config.num_subsweeps):
            return

        config = copy.deepcopy(self._sensor_config)
        config._subsweeps[index] = subsweep_config
        self.set_data(config)
        self.sig_update.emit(config)

    def _update_sensor_config_aspect(self, aspect: str, value: Any) -> None:
        if self._sensor_config is None:
            msg = "SensorConfig is None"
            raise TypeError(msg)

        config = copy.deepcopy(self._sensor_config)

        try:
            setattr(config, aspect, value)
        except Exception as e:
            self._sensor_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
            self._erroneous_aspects.add(aspect)

            # this emit needs to be done to signal that "is_ready" has changed.
            self.sig_update.emit(self.get_data())
        else:
            self._erroneous_aspects.discard(aspect)

            self.set_data(config)
            self.sig_update.emit(config)
