from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .types import PidgetMapping


log = logging.getLogger(__name__)


class SessionConfigEditor(QWidget):
    sig_session_config_updated = Signal(a121.SessionConfig)

    _session_config: Optional[a121.SessionConfig]

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._session_config = None
        self._layout = QVBoxLayout()
        self.setLayout(self._layout)
        self._session_config_pidgets: PidgetMapping = {
            "update_rate": (
                pidgets.OptionalTextParameterWidget("Update rate:", parent=self),
                lambda val: None if (val is None) else float(val),
            )
        }
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
                pidgets.EnumParameterWidget(a121.IdleState, "Inter frame idle state:"),
                a121.IdleState,
            ),
            "inter_sweep_idle_state": (
                pidgets.EnumParameterWidget(a121.IdleState, "Inter sweep idle state:"),
                a121.IdleState,
            ),
        }
        self._subsweep_config_pidgets: PidgetMapping = {
            "start_point": (pidgets.TextParameterWidget("Start point:", parent=self), int),
            "num_points": (pidgets.TextParameterWidget("Number of points:", parent=self), int),
            "step_length": (pidgets.TextParameterWidget("Step length:", parent=self), int),
            "profile": (pidgets.EnumParameterWidget(a121.Profile, "Profile:"), a121.Profile),
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
            "prf": (pidgets.EnumParameterWidget(a121.PRF, "PRF"), a121.PRF),
        }

        self._all_pidgets = []
        for aspect, (pidget, func) in self._session_config_pidgets.items():
            self._setup_session_config_pidget(pidget, aspect, func)
            self._all_pidgets.append(pidget)

        for aspect, (pidget, func) in self._sensor_config_pidgets.items():
            self._setup_sensor_config_pidget(pidget, aspect, func)
            self._all_pidgets.append(pidget)

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

    def _add_pidget_to_layout(self, pidget: pidgets.ParameterWidget) -> None:
        self._layout.addWidget(pidget)

    def _setup_session_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self._add_pidget_to_layout(pidget)
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_session_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_sensor_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self._add_pidget_to_layout(pidget)
        pidget.sig_parameter_changed.connect(
            lambda val: self._update_sensor_config_aspect(
                aspect, val if (func is None) else func(val)
            )
        )

    def _setup_subsweep_config_pidget(
        self, pidget: pidgets.ParameterWidget, aspect: str, func: Optional[Callable[[Any], Any]]
    ) -> None:
        self._add_pidget_to_layout(pidget)
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
