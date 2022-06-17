from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .types import PidgetMapping
from .utils import VerticalGroupBox


log = logging.getLogger(__name__)


class SessionConfigEditor(QWidget):
    _session_config: Optional[a121.SessionConfig]
    _all_pidgets: list[pidgets.ParameterWidget]

    IDLE_STATE_LABEL_MAP = {
        a121.IdleState.DEEP_SLEEP: "Deep sleep",
        a121.IdleState.SLEEP: "Sleep",
        a121.IdleState.READY: "Ready",
    }
    PROFILE_LABEL_MAP = {member: str(member.value) for member in a121.Profile}
    PRF_LABEL_MAP = {
        a121.PRF.PRF_19_5_MHz: "19.5 MHz",
        a121.PRF.PRF_13_0_MHz: "13.0 MHz",
        a121.PRF.PRF_8_7_MHz: "8.7 MHz",
        a121.PRF.PRF_6_5_MHz: "6.5 MHz",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._session_config = None
        self._all_pidgets = []

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(11)

        # Session pidgets
        self.session_group_box = VerticalGroupBox("Session parameters", parent=self)
        self._session_config_pidgets: PidgetMapping = {
            "update_rate": (
                pidgets.OptionalTextParameterWidget("Update rate:", parent=self),
                lambda val: None if (val is None) else float(val),
            )
        }
        for aspect, (pidget, func) in self._session_config_pidgets.items():
            self._setup_session_config_pidget(pidget, aspect, func)
            self._all_pidgets.append(pidget)
        self.layout().addWidget(self.session_group_box)

        # Sensor pidgets
        self.sensor_group_box = VerticalGroupBox("Sensor parameters", parent=self)
        self._sensor_config_pidgets: PidgetMapping = {
            "sweeps_per_frame": (
                pidgets.TextParameterWidget("Sweeps per frame:", parent=self),
                int,
            ),
            "sweep_rate": (
                pidgets.OptionalTextParameterWidget("Sweep rate:", parent=self),
                lambda val: None if (val is None) else float(val),
            ),
            "frame_rate": (
                pidgets.OptionalTextParameterWidget("Frame rate:", parent=self),
                lambda val: None if (val is None) else float(val),
            ),
            "continuous_sweep_mode": (
                pidgets.CheckboxParameterWidget("Continuous sweep mode:", parent=self),
                bool,
            ),
            "inter_frame_idle_state": (
                pidgets.EnumParameterWidget(
                    a121.IdleState,
                    "Inter frame idle state:",
                    label_mapping=self.IDLE_STATE_LABEL_MAP,
                ),
                a121.IdleState,
            ),
            "inter_sweep_idle_state": (
                pidgets.EnumParameterWidget(
                    a121.IdleState,
                    "Inter sweep idle state:",
                    label_mapping=self.IDLE_STATE_LABEL_MAP,
                ),
                a121.IdleState,
            ),
        }
        for aspect, (pidget, func) in self._sensor_config_pidgets.items():
            self._setup_sensor_config_pidget(pidget, aspect, func)
            self._all_pidgets.append(pidget)
        self.layout().addWidget(self.sensor_group_box)

        # Subsweeps pidgets
        self.subsweep_group_box = VerticalGroupBox(
            "Subsweep-specific parameters", parent=self.session_group_box
        )
        self.sensor_group_box.layout().addWidget(self.subsweep_group_box)

        self._subsweep_config_pidgets: PidgetMapping = {
            "start_point": (pidgets.TextParameterWidget("Start point:", parent=self), int),
            "num_points": (pidgets.TextParameterWidget("Number of points:", parent=self), int),
            "step_length": (pidgets.TextParameterWidget("Step length:", parent=self), int),
            "profile": (
                pidgets.EnumParameterWidget(
                    a121.Profile, "Profile:", parent=self, label_mapping=self.PROFILE_LABEL_MAP
                ),
                a121.Profile,
            ),
            "hwaas": (pidgets.TextParameterWidget("HWAAS:", parent=self), int),
            "receiver_gain": (pidgets.TextParameterWidget("Receiver gain:", parent=self), int),
            "enable_tx": (
                pidgets.CheckboxParameterWidget("Enable transmitter:", parent=self),
                bool,
            ),
            "enable_loopback": (
                pidgets.CheckboxParameterWidget("Enable loopback:", parent=self),
                bool,
            ),
            "phase_enhancement": (
                pidgets.CheckboxParameterWidget("Phase enhancement:", parent=self),
                bool,
            ),
            "prf": (
                pidgets.EnumParameterWidget(
                    a121.PRF, "PRF", parent=self, label_mapping=self.PRF_LABEL_MAP
                ),
                a121.PRF,
            ),
        }

        for aspect, (pidget, func) in self._subsweep_config_pidgets.items():
            self._setup_subsweep_config_pidget(pidget, aspect, func)
            self._all_pidgets.append(pidget)

    @property
    def session_config(self) -> Optional[a121.SessionConfig]:
        return self._session_config

    @session_config.setter
    def session_config(self, session_config: Optional[a121.SessionConfig]) -> None:
        if session_config is None:
            self.setEnabled(False)
        else:
            self._session_config = session_config
            self.setEnabled(True)
            self._update_ui()

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
            self._session_config_pidgets[aspect][0].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

    def _update_sensor_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        try:
            setattr(self._session_config.sensor_config, aspect, value)
        except Exception as e:
            self._sensor_config_pidgets[aspect][0].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

    def _update_subsweep_config_aspect(self, aspect: str, value: Any) -> None:
        if self._session_config is None:
            raise TypeError("SessionConfig is None")

        try:
            setattr(self._session_config.sensor_config.subsweep, aspect, value)
        except Exception as e:
            self._subsweep_config_pidgets[aspect][0].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._handle_validation_results(self._session_config._collect_validation_results())

    def _setup_session_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self.session_group_box.layout().addWidget(pidget)
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_session_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_sensor_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self.sensor_group_box.layout().addWidget(pidget)
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_sensor_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_subsweep_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self.subsweep_group_box.layout().addWidget(pidget)
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

        pidget_map[result.aspect][0].set_note_text(result.message, result.criticality)

    def _update_ui(self) -> None:
        if self._session_config is None:
            log.debug("could not update ui as SessionConfig is None")
            return

        self._session_config_pidgets["update_rate"][0].set_parameter(
            self._session_config.update_rate
        )

        sensor_config = self._session_config.sensor_config
        self._sensor_config_pidgets["sweeps_per_frame"][0].set_parameter(
            sensor_config.sweeps_per_frame
        )
        self._sensor_config_pidgets["sweep_rate"][0].set_parameter(sensor_config.sweep_rate)
        self._sensor_config_pidgets["frame_rate"][0].set_parameter(sensor_config.frame_rate)
        self._sensor_config_pidgets["continuous_sweep_mode"][0].set_parameter(
            sensor_config.continuous_sweep_mode
        )
        self._sensor_config_pidgets["inter_frame_idle_state"][0].set_parameter(
            sensor_config.inter_frame_idle_state
        )
        self._sensor_config_pidgets["inter_sweep_idle_state"][0].set_parameter(
            sensor_config.inter_sweep_idle_state
        )

        subsweep_config = sensor_config.subsweep
        self._subsweep_config_pidgets["start_point"][0].set_parameter(subsweep_config.start_point)
        self._subsweep_config_pidgets["num_points"][0].set_parameter(subsweep_config.num_points)
        self._subsweep_config_pidgets["step_length"][0].set_parameter(subsweep_config.step_length)
        self._subsweep_config_pidgets["profile"][0].set_parameter(subsweep_config.profile)
        self._subsweep_config_pidgets["hwaas"][0].set_parameter(subsweep_config.hwaas)
        self._subsweep_config_pidgets["receiver_gain"][0].set_parameter(
            subsweep_config.receiver_gain
        )
        self._subsweep_config_pidgets["enable_tx"][0].set_parameter(subsweep_config.enable_tx)
        self._subsweep_config_pidgets["enable_loopback"][0].set_parameter(
            subsweep_config.enable_loopback
        )
        self._subsweep_config_pidgets["phase_enhancement"][0].set_parameter(
            subsweep_config.phase_enhancement
        )
        self._subsweep_config_pidgets["prf"][0].set_parameter(subsweep_config.prf)
