# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from functools import partial
from typing import Any, Mapping, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabWidget, QToolButton, QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .subsweep_config_editor import SubsweepConfigEditor
from .types import PidgetFactoryMapping
from .utils import VerticalGroupBox


log = logging.getLogger(__name__)


class SensorConfigEditor(QWidget):
    sig_update = Signal(object)

    _sensor_config: Optional[a121.SensorConfig]
    _subsweep_config_editors: list[SubsweepConfigEditor]

    _all_pidgets: list[pidgets.ParameterWidget]

    SPACING = 15
    IDLE_STATE_LABEL_MAP = {
        a121.IdleState.READY: "Ready",
        a121.IdleState.SLEEP: "Sleep",
        a121.IdleState.DEEP_SLEEP: "Deep sleep",
    }
    SENSOR_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "sweeps_per_frame": pidgets.IntParameterWidgetFactory(
            name_label_text="Sweeps per frame:",
            name_label_tooltip=(
                "The number of sweeps that will be captured in each frame (measurement)."
            ),
            limits=(1, 4095),
        ),
        "sweep_rate": pidgets.OptionalFloatParameterWidgetFactory(
            name_label_text="Sweep rate:",
            name_label_tooltip=(
                "The sweep rate for sweeps in a frame (measurement).\n"
                "If 'Limit' is unchecked, the sweep rate will be as fast as possible."
            ),
            limits=(1, 1e6),
            decimals=0,
            init_set_value=1000.0,
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "frame_rate": pidgets.OptionalFloatParameterWidgetFactory(
            name_label_text="Frame rate:",
            name_label_tooltip=(
                "Frame rate.\nIf 'Limit' is unchecked, the rate is not limited by the sensor "
                "but by the rate that the server acknowledge and reads out the frame."
            ),
            limits=(0.1, 1e4),
            decimals=1,
            init_set_value=10.0,
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "inter_sweep_idle_state": pidgets.EnumParameterWidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter sweep idle state:",
            name_label_tooltip=(
                "The inter sweep idle state is the state the sensor idles in "
                "between each sweep in a frame."
            ),
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "inter_frame_idle_state": pidgets.EnumParameterWidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter frame idle state:",
            name_label_tooltip=(
                "The inter frame idle state is the state the sensor idles in between each frame."
            ),
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "continuous_sweep_mode": pidgets.CheckboxParameterWidgetFactory(
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
        "double_buffering": pidgets.CheckboxParameterWidgetFactory(
            name_label_text="Double buffering",
            name_label_tooltip=(
                "Double buffering will split the sensor buffer in two halves. "
                "One half is used to read out the frame while sampling is done "
                "in the other half."
            ),
        ),
    }

    def __init__(
        self, supports_multiple_subsweeps: bool = False, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)

        self._all_pidgets = []

        self._sensor_config = None
        self._subsweep_config_editors = []

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.sensor_group_box = VerticalGroupBox("Sensor parameters", parent=self)
        self.sensor_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.sensor_group_box)

        self._sensor_config_pidgets: Mapping[str, pidgets.ParameterWidget] = {}
        for aspect, factory in self.SENSOR_CONFIG_FACTORIES.items():
            pidget = factory.create(self.sensor_group_box)
            self.sensor_group_box.layout().addWidget(pidget)

            pidget.sig_parameter_changed.connect(
                partial(self._update_sensor_config_aspect, aspect)
            )

            self._all_pidgets.append(pidget)
            self._sensor_config_pidgets[aspect] = pidget

        self.subsweep_group_box = VerticalGroupBox("Subsweep parameters", parent=self)
        self.subsweep_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.subsweep_group_box)

        self._tab_widget = QTabWidget(self)
        self._tab_widget.setStyleSheet("QTabWidget::pane { padding: 5px;}")
        self.subsweep_group_box.layout().addWidget(self._tab_widget)

        if supports_multiple_subsweeps:
            self._tab_widget.setTabsClosable(True)
            self._tab_widget.tabCloseRequested.connect(self._remove_subsweep_config)

            self._plus_button = QToolButton(self)
            self._plus_button.setText("+")
            self.layout().addWidget(self._plus_button)
            self._plus_button.clicked.connect(self._add_subsweep_config)
            self._tab_widget.setCornerWidget(self._plus_button)
            self._tab_widget.cornerWidget().setMinimumSize(self._plus_button.sizeHint())

    def _add_subsweep_config(self) -> None:
        if self._sensor_config is None:
            return
        if self._tab_widget.count() > 3:
            return
        subsweep_config = a121.SubsweepConfig()
        self._sensor_config._subsweeps.append(subsweep_config)
        self._broadcast()
        subsweep_config_editor = self._add_subsweep_config_editor()
        subsweep_config_editor.set_data(subsweep_config)
        subsweep_config_editor.sync()

    def _add_tabs(self, tabs_needed: int) -> None:
        while self._tab_widget.count() < tabs_needed:
            self._add_subsweep_config_editor()

    def _add_subsweep_config_editor(self) -> SubsweepConfigEditor:
        subsweep_config_editor = SubsweepConfigEditor(self)
        self._subsweep_config_editors.append(subsweep_config_editor)
        subsweep_config_editor.sig_update.connect(self._broadcast)
        self._tab_widget.addTab(subsweep_config_editor, str(len(self._subsweep_config_editors)))
        self._update_tab_labels()
        return subsweep_config_editor

    def _remove_subsweep_config(self, idx: int) -> None:
        if self._sensor_config is None:
            return
        if self._tab_widget.count() < 2:
            return
        self._sensor_config.subsweeps.pop(idx)
        self._broadcast()
        self._remove_subsweep_config_editor(idx)

    def _remove_tabs(self, tabs_needed: int) -> None:
        while self._tab_widget.count() > tabs_needed:
            self._remove_subsweep_config_editor(0)

    def _remove_subsweep_config_editor(self, idx: int) -> None:
        self._tab_widget.removeTab(idx)
        self._subsweep_config_editors.pop(idx)
        self._update_tab_labels()

    def _update_tab_labels(self) -> None:
        for tab_idx in range(self._tab_widget.count()):
            self._tab_widget.setTabText(tab_idx, f"{tab_idx + 1}      ")

    def _update_ui(self) -> None:
        if self._sensor_config is None:
            log.debug("could not update ui as SensorConfig is None")
            return

        self._sensor_config_pidgets["sweeps_per_frame"].set_parameter(
            self._sensor_config.sweeps_per_frame
        )
        self._sensor_config_pidgets["sweep_rate"].set_parameter(self._sensor_config.sweep_rate)
        self._sensor_config_pidgets["frame_rate"].set_parameter(self._sensor_config.frame_rate)
        self._sensor_config_pidgets["continuous_sweep_mode"].set_parameter(
            self._sensor_config.continuous_sweep_mode
        )
        self._sensor_config_pidgets["double_buffering"].set_parameter(
            self._sensor_config.double_buffering
        )
        self._sensor_config_pidgets["inter_frame_idle_state"].set_parameter(
            self._sensor_config.inter_frame_idle_state
        )
        self._sensor_config_pidgets["inter_sweep_idle_state"].set_parameter(
            self._sensor_config.inter_sweep_idle_state
        )

    def set_data(self, sensor_config: Optional[a121.SensorConfig]) -> None:
        self._sensor_config = sensor_config
        if sensor_config is None:
            return
        tabs_needed = len(sensor_config.subsweeps)
        self._remove_tabs(tabs_needed)
        self._add_tabs(tabs_needed)
        for i, subsweep in enumerate(sensor_config.subsweeps):
            self._subsweep_config_editors[i].set_data(subsweep)

    def sync(self) -> None:
        self._update_ui()
        for subsweep_config_editor in self._subsweep_config_editors:
            subsweep_config_editor.sync()

    def _broadcast(self) -> None:
        self.sig_update.emit(self._sensor_config)

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        for pidget in self._all_pidgets:
            pidget.set_note_text("")

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        for subsweep_config_editor in self._subsweep_config_editors:
            unhandled_results = subsweep_config_editor.handle_validation_results(unhandled_results)

        return unhandled_results

    def _handle_validation_result(self, result: a121.ValidationResult) -> bool:
        if result.aspect is None or self._sensor_config is None:
            return False

        result_handled = False

        if result.source == self._sensor_config:
            for pidget in self._sensor_config_pidgets:
                if result.aspect == pidget:
                    self._sensor_config_pidgets[result.aspect].set_note_text(
                        result.message, result.criticality
                    )
                    result_handled = True

        return result_handled

    def _update_sensor_config_aspect(self, aspect: str, value: Any) -> None:
        if self._sensor_config is None:
            raise TypeError("SensorConfig is None")

        try:
            setattr(self._sensor_config, aspect, value)
        except Exception as e:
            self._sensor_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)

        self._broadcast()
