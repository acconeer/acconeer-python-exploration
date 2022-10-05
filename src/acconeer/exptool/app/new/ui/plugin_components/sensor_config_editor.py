# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
from functools import partial
from typing import Any, Mapping, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

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

    _all_pidgets: list[pidgets.ParameterWidget]

    SPACING = 15
    IDLE_STATE_LABEL_MAP = {
        a121.IdleState.READY: "Ready",
        a121.IdleState.SLEEP: "Sleep",
        a121.IdleState.DEEP_SLEEP: "Deep sleep",
    }
    PROFILE_LABEL_MAP = {
        a121.Profile.PROFILE_1: "1 (shortest)",
        a121.Profile.PROFILE_2: "2",
        a121.Profile.PROFILE_3: "3",
        a121.Profile.PROFILE_4: "4",
        a121.Profile.PROFILE_5: "5 (longest)",
    }
    PRF_LABEL_MAP = {
        a121.PRF.PRF_19_5_MHz: "19.5 MHz",
        a121.PRF.PRF_13_0_MHz: "13.0 MHz",
        a121.PRF.PRF_8_7_MHz: "8.7 MHz",
        a121.PRF.PRF_6_5_MHz: "6.5 MHz",
    }
    SENSOR_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "sweeps_per_frame": pidgets.IntParameterWidgetFactory(
            name_label_text="Sweeps per frame:",
            limits=(1, 4095),
        ),
        "sweep_rate": pidgets.OptionalFloatParameterWidgetFactory(
            name_label_text="Sweep rate:",
            limits=(1, 1e6),
            decimals=0,
            init_set_value=1000.0,
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "frame_rate": pidgets.OptionalFloatParameterWidgetFactory(
            name_label_text="Frame rate:",
            limits=(0.1, 1e4),
            decimals=1,
            init_set_value=10.0,
            suffix="Hz",
            checkbox_label_text="Limit",
        ),
        "inter_sweep_idle_state": pidgets.EnumParameterWidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter sweep idle state:",
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "inter_frame_idle_state": pidgets.EnumParameterWidgetFactory(
            enum_type=a121.IdleState,
            name_label_text="Inter frame idle state:",
            label_mapping=IDLE_STATE_LABEL_MAP,
        ),
        "continuous_sweep_mode": pidgets.CheckboxParameterWidgetFactory(
            name_label_text="Continuous sweep mode",
        ),
        "double_buffering": pidgets.CheckboxParameterWidgetFactory(
            name_label_text="Enable double buffering",
        ),
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._all_pidgets = []

        self._sensor_config = None

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

        self._subsweep_config_editor = SubsweepConfigEditor(self)
        self._subsweep_config_editor.sig_update.connect(self._broadcast)
        self.sensor_group_box.layout().addWidget(self._subsweep_config_editor)

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
        self._sensor_config_pidgets["inter_frame_idle_state"].set_parameter(
            self._sensor_config.inter_frame_idle_state
        )
        self._sensor_config_pidgets["inter_sweep_idle_state"].set_parameter(
            self._sensor_config.inter_sweep_idle_state
        )

    def set_data(self, sensor_config: Optional[a121.SensorConfig]) -> None:
        self._sensor_config = sensor_config
        if sensor_config is not None:
            self._subsweep_config_editor.set_data(sensor_config.subsweep)
            self._handle_validation_results(sensor_config._collect_validation_results())

    def sync(self) -> None:
        self._update_ui()
        self._subsweep_config_editor.sync()

    def _broadcast(self) -> None:
        self.sig_update.emit(self._sensor_config)

    def _handle_validation_results(self, results: list[a121.ValidationResult]) -> None:
        for pidget in self._all_pidgets:
            pidget.set_note_text("")

        for result in results:
            self._handle_validation_result(result)

    def _handle_validation_result(self, result: a121.ValidationResult) -> None:
        if result.aspect is None or self._sensor_config is None:
            return

        if result.source == self._sensor_config:
            self._sensor_config_pidgets[result.aspect].set_note_text(
                result.message, result.criticality
            )

    def _update_sensor_config_aspect(self, aspect: str, value: Any) -> None:
        if self._sensor_config is None:
            raise TypeError("SensorConfig is None")

        try:
            setattr(self._sensor_config, aspect, value)
        except Exception as e:
            self._sensor_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._sensor_config._collect_validation_results())

        self._broadcast()
