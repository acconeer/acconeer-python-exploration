from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .range_help_view import RangeHelpView
from .types import PidgetFactoryMapping
from .utils import VerticalGroupBox


log = logging.getLogger(__name__)


class SessionConfigEditor(QWidget):
    _session_config: Optional[a121.SessionConfig]
    _all_pidgets: list[pidgets.ParameterWidget]

    sig_update = Signal(object)

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
    SESSION_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "update_rate": (
            pidgets.OptionalFloatParameterWidgetFactory(
                name_label_text="Update rate:",
                limits=(0.1, 1e4),
                decimals=1,
                init_set_value=10.0,
                suffix="Hz",
                checkbox_label_text="Limit",
            ),
            lambda val: None if (val is None) else float(val),
        )
    }
    SENSOR_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "sweeps_per_frame": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="Sweeps per frame:",
                limits=(1, 4095),
            ),
            int,
        ),
        "sweep_rate": (
            pidgets.OptionalFloatParameterWidgetFactory(
                name_label_text="Sweep rate:",
                limits=(1, 1e6),
                decimals=0,
                init_set_value=1000.0,
                suffix="Hz",
                checkbox_label_text="Limit",
            ),
            lambda val: None if (val is None) else float(val),
        ),
        "frame_rate": (
            pidgets.OptionalFloatParameterWidgetFactory(
                name_label_text="Frame rate:",
                limits=(0.1, 1e4),
                decimals=1,
                init_set_value=10.0,
                suffix="Hz",
                checkbox_label_text="Limit",
            ),
            lambda val: None if (val is None) else float(val),
        ),
        "continuous_sweep_mode": (
            pidgets.CheckboxParameterWidgetFactory(
                name_label_text="Continuous sweep mode:",
            ),
            bool,
        ),
        "inter_sweep_idle_state": (
            pidgets.EnumParameterWidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter sweep idle state:",
                label_mapping=IDLE_STATE_LABEL_MAP,
            ),
            a121.IdleState,
        ),
        "inter_frame_idle_state": (
            pidgets.EnumParameterWidgetFactory(
                enum_type=a121.IdleState,
                name_label_text="Inter frame idle state:",
                label_mapping=IDLE_STATE_LABEL_MAP,
            ),
            a121.IdleState,
        ),
    }
    SUBSWEEP_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "start_point": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="Start point:",
            ),
            int,
        ),
        "num_points": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="Number of points:",
                limits=(1, 4095),
            ),
            int,
        ),
        "step_length": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="Step length:",
                limits=(1, None),
            ),
            int,
        ),
        "profile": (
            pidgets.EnumParameterWidgetFactory(
                enum_type=a121.Profile,
                name_label_text="Profile:",
                label_mapping=PROFILE_LABEL_MAP,
            ),
            a121.Profile,
        ),
        "hwaas": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="HWAAS:",
                limits=(1, 511),
            ),
            int,
        ),
        "receiver_gain": (
            pidgets.IntParameterWidgetFactory(
                name_label_text="Receiver gain:",
                limits=(0, 23),
            ),
            int,
        ),
        "enable_tx": (
            pidgets.CheckboxParameterWidgetFactory(
                name_label_text="Enable transmitter:",
            ),
            bool,
        ),
        "enable_loopback": (
            pidgets.CheckboxParameterWidgetFactory(
                name_label_text="Enable loopback:",
            ),
            bool,
        ),
        "phase_enhancement": (
            pidgets.CheckboxParameterWidgetFactory(
                name_label_text="Phase enhancement:",
            ),
            bool,
        ),
        "prf": (
            pidgets.EnumParameterWidgetFactory(
                enum_type=a121.PRF,
                name_label_text="PRF:",
                label_mapping=PRF_LABEL_MAP,
            ),
            a121.PRF,
        ),
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._session_config = None
        self._all_pidgets = []

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        # Session pidgets

        self.session_group_box = VerticalGroupBox("Session parameters", parent=self)
        self.session_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.session_group_box)

        self._session_config_pidgets: Mapping[str, pidgets.ParameterWidget] = {}
        for aspect, (factory, func) in self.SESSION_CONFIG_FACTORIES.items():
            pidget = factory.create(self.session_group_box)
            self.session_group_box.layout().addWidget(pidget)

            self._setup_session_config_pidget(pidget, aspect, func)

            self._all_pidgets.append(pidget)
            self._session_config_pidgets[aspect] = pidget

        # Sensor pidgets

        self.sensor_group_box = VerticalGroupBox("Sensor parameters", parent=self)
        self.sensor_group_box.layout().setSpacing(self.SPACING)
        self.layout().addWidget(self.sensor_group_box)

        self._sensor_config_pidgets: Mapping[str, pidgets.ParameterWidget] = {}
        for aspect, (factory, func) in self.SENSOR_CONFIG_FACTORIES.items():
            pidget = factory.create(self.sensor_group_box)
            self.sensor_group_box.layout().addWidget(pidget)

            self._setup_sensor_config_pidget(pidget, aspect, func)

            self._all_pidgets.append(pidget)
            self._sensor_config_pidgets[aspect] = pidget

        # Subsweeps pidgets

        self.subsweep_group_box = VerticalGroupBox(
            "Subsweep-specific parameters", parent=self.session_group_box
        )
        self.subsweep_group_box.layout().setSpacing(self.SPACING)
        self.sensor_group_box.layout().addWidget(self.subsweep_group_box)

        self.range_help_view = RangeHelpView(self.subsweep_group_box)
        self.subsweep_group_box.layout().addWidget(self.range_help_view)

        self._subsweep_config_pidgets: Mapping[str, pidgets.ParameterWidget] = {}
        for aspect, (factory, func) in self.SUBSWEEP_CONFIG_FACTORIES.items():
            pidget = factory.create(self.subsweep_group_box)
            self.subsweep_group_box.layout().addWidget(pidget)

            self._setup_subsweep_config_pidget(pidget, aspect, func)

            self._all_pidgets.append(pidget)
            self._subsweep_config_pidgets[aspect] = pidget

    def set_data(self, session_config: Optional[a121.SessionConfig]) -> None:
        self._session_config = session_config
        self.range_help_view.update(
            session_config.sensor_config.subsweep if session_config else None
        )

    def sync(self) -> None:
        self._update_ui()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled and self._session_config is not None)

    def _broadcast(self) -> None:
        self.sig_update.emit(self._session_config)

    def _handle_validation_results(self, results: list[a121.ValidationResult]) -> None:
        if results == []:
            for pidget in self._all_pidgets:
                pidget.set_note_text("")
        else:
            for result in results:
                self._handle_validation_result(result)

    def _update_session_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")
        try:
            setattr(self._session_config, aspect, value)
        except Exception as e:
            self._session_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

        self._broadcast()

    def _update_sensor_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        try:
            setattr(self._session_config.sensor_config, aspect, value)
        except Exception as e:
            self._sensor_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

        self._broadcast()

    def _update_subsweep_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        try:
            setattr(self._session_config.sensor_config.subsweep, aspect, value)
        except Exception as e:
            self._subsweep_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

        self._broadcast()

    def _setup_session_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_session_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_sensor_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_sensor_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_subsweep_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_subsweep_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _handle_validation_result(self, result: a121.ValidationResult) -> None:
        if result.aspect is None or self._session_config is None:
            return

        if result.source is self._session_config:
            pidget_map = self._session_config_pidgets
        elif result.source is self._session_config.sensor_config:
            pidget_map = self._sensor_config_pidgets
        elif result.source is self._session_config.sensor_config.subsweep:
            pidget_map = self._subsweep_config_pidgets
        else:
            return

        pidget_map[result.aspect].set_note_text(result.message, result.criticality)

    def _update_ui(self) -> None:
        if self._session_config is None:
            log.debug("could not update ui as SessionConfig is None")
            return

        self._session_config_pidgets["update_rate"].set_parameter(self._session_config.update_rate)

        sensor_config = self._session_config.sensor_config
        self._sensor_config_pidgets["sweeps_per_frame"].set_parameter(
            sensor_config.sweeps_per_frame
        )
        self._sensor_config_pidgets["sweep_rate"].set_parameter(sensor_config.sweep_rate)
        self._sensor_config_pidgets["frame_rate"].set_parameter(sensor_config.frame_rate)
        self._sensor_config_pidgets["continuous_sweep_mode"].set_parameter(
            sensor_config.continuous_sweep_mode
        )
        self._sensor_config_pidgets["inter_frame_idle_state"].set_parameter(
            sensor_config.inter_frame_idle_state
        )
        self._sensor_config_pidgets["inter_sweep_idle_state"].set_parameter(
            sensor_config.inter_sweep_idle_state
        )

        subsweep_config = sensor_config.subsweep
        self._subsweep_config_pidgets["start_point"].set_parameter(subsweep_config.start_point)
        self._subsweep_config_pidgets["num_points"].set_parameter(subsweep_config.num_points)
        self._subsweep_config_pidgets["step_length"].set_parameter(subsweep_config.step_length)
        self._subsweep_config_pidgets["profile"].set_parameter(subsweep_config.profile)
        self._subsweep_config_pidgets["hwaas"].set_parameter(subsweep_config.hwaas)
        self._subsweep_config_pidgets["receiver_gain"].set_parameter(subsweep_config.receiver_gain)
        self._subsweep_config_pidgets["enable_tx"].set_parameter(subsweep_config.enable_tx)
        self._subsweep_config_pidgets["enable_loopback"].set_parameter(
            subsweep_config.enable_loopback
        )
        self._subsweep_config_pidgets["phase_enhancement"].set_parameter(
            subsweep_config.phase_enhancement
        )
        self._subsweep_config_pidgets["prf"].set_parameter(subsweep_config.prf)
