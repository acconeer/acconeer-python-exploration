# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import logging
from functools import partial
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from . import pidgets
from .collapsible_widget import CollapsibleWidget
from .range_help_view import RangeHelpView
from .types import PidgetFactoryMapping


log = logging.getLogger(__name__)


class SubsweepConfigEditor(QWidget):
    sig_update = Signal(object)

    _subsweep_config: Optional[a121.SubsweepConfig]

    _subsweep_config_pidgets: dict[str, pidgets.Pidget]
    _erroneous_aspects: set[str]

    SPACING = 15
    PROFILE_LABEL_MAP = {
        a121.Profile.PROFILE_1: "1 (shortest)",
        a121.Profile.PROFILE_2: "2",
        a121.Profile.PROFILE_3: "3",
        a121.Profile.PROFILE_4: "4",
        a121.Profile.PROFILE_5: "5 (longest)",
    }
    PRF_LABEL_MAP = {
        a121.PRF.PRF_19_5_MHz: "19.5 MHz",
        a121.PRF.PRF_15_6_MHz: "15.6 MHz",
        a121.PRF.PRF_13_0_MHz: "13.0 MHz",
        a121.PRF.PRF_8_7_MHz: "8.7 MHz",
        a121.PRF.PRF_6_5_MHz: "6.5 MHz",
        a121.PRF.PRF_5_2_MHz: "5.2 MHz",
    }
    SUBSWEEP_CONFIG_FACTORIES: PidgetFactoryMapping = {
        "start_point": pidgets.IntPidgetFactory(
            name_label_text="Start point:",
            name_label_tooltip=a121.SubsweepConfig.start_point.__doc__,
        ),
        "num_points": pidgets.IntPidgetFactory(
            name_label_text="Number of points:",
            name_label_tooltip=a121.SubsweepConfig.num_points.__doc__,
            limits=(1, 4095),
        ),
        "step_length": pidgets.IntPidgetFactory(
            name_label_text="Step length:",
            name_label_tooltip=a121.SubsweepConfig.step_length.__doc__,
            limits=(1, None),
        ),
        "hwaas": pidgets.IntPidgetFactory(
            name_label_text="HWAAS:",
            name_label_tooltip=a121.SubsweepConfig.hwaas.__doc__,
            limits=(1, 511),
        ),
        "receiver_gain": pidgets.IntPidgetFactory(
            name_label_text="Receiver gain:",
            name_label_tooltip=a121.SubsweepConfig.receiver_gain.__doc__,
            limits=(0, 23),
        ),
        "profile": pidgets.EnumPidgetFactory(
            enum_type=a121.Profile,
            name_label_text="Profile:",
            name_label_tooltip=a121.SubsweepConfig.profile.__doc__,  # type: ignore[arg-type]
            label_mapping=PROFILE_LABEL_MAP,
        ),
        "prf": pidgets.EnumPidgetFactory(
            enum_type=a121.PRF,
            name_label_text="PRF:",
            name_label_tooltip=a121.SubsweepConfig.prf.__doc__,  # type: ignore[arg-type]
            label_mapping=PRF_LABEL_MAP,
        ),
        "enable_tx": pidgets.CheckboxPidgetFactory(
            name_label_text="Enable transmitter",
            name_label_tooltip=a121.SubsweepConfig.enable_tx.__doc__,
        ),
        "enable_loopback": pidgets.CheckboxPidgetFactory(
            name_label_text="Enable loopback",
            name_label_tooltip=a121.SubsweepConfig.enable_loopback.__doc__,
        ),
        "phase_enhancement": pidgets.CheckboxPidgetFactory(
            name_label_text="Phase enhancement",
            name_label_tooltip=a121.SubsweepConfig.phase_enhancement.__doc__,
        ),
    }
    ADVANCED_PARAMETERS = {
        "receiver_gain",
        "prf",
        "enable_tx",
        "enable_loopback",
        "phase_enhancement",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._subsweep_config_pidgets = {}
        self._erroneous_aspects = set()

        self._subsweep_config = None

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.range_help_view = RangeHelpView(self)
        self.layout().addWidget(self.range_help_view)

        collapsible_layout = QVBoxLayout()

        for aspect, factory in self.SUBSWEEP_CONFIG_FACTORIES.items():
            pidget = factory.create(self)

            if aspect in self.ADVANCED_PARAMETERS:
                collapsible_layout.addWidget(pidget)
            else:
                self.layout().addWidget(pidget)

            pidget.sig_parameter_changed.connect(
                partial(self._update_subsweep_config_aspect, aspect)
            )

            self._subsweep_config_pidgets[aspect] = pidget

        # Some left margin here will show the hierarchy
        collapsible_layout.setContentsMargins(11, 0, 0, 0)
        dummy = QWidget()
        dummy.setLayout(collapsible_layout)
        self.layout().addWidget(
            CollapsibleWidget(
                label="Advanced",
                widget=dummy,
            )
        )

    def sync(self) -> None:
        self._update_ui()

    def _update_ui(self) -> None:
        if self._subsweep_config is None:
            log.debug("could not update ui as SubsweepConfig is None")
            return

        self._subsweep_config_pidgets["start_point"].set_parameter(
            self._subsweep_config.start_point
        )
        self._subsweep_config_pidgets["num_points"].set_parameter(self._subsweep_config.num_points)
        self._subsweep_config_pidgets["step_length"].set_parameter(
            self._subsweep_config.step_length
        )
        self._subsweep_config_pidgets["profile"].set_parameter(self._subsweep_config.profile)
        self._subsweep_config_pidgets["hwaas"].set_parameter(self._subsweep_config.hwaas)
        self._subsweep_config_pidgets["receiver_gain"].set_parameter(
            self._subsweep_config.receiver_gain
        )
        self._subsweep_config_pidgets["enable_tx"].set_parameter(self._subsweep_config.enable_tx)
        self._subsweep_config_pidgets["enable_loopback"].set_parameter(
            self._subsweep_config.enable_loopback
        )
        self._subsweep_config_pidgets["phase_enhancement"].set_parameter(
            self._subsweep_config.phase_enhancement
        )
        self._subsweep_config_pidgets["prf"].set_parameter(self._subsweep_config.prf)

    def set_data(self, subsweep_config: Optional[a121.SubsweepConfig]) -> None:
        self.range_help_view.update(subsweep_config)
        self._subsweep_config = subsweep_config

    @property
    def is_ready(self) -> bool:
        return self._erroneous_aspects == set()

    def set_read_only(self, read_only: bool) -> None:
        for pidget in self._subsweep_config_pidgets.values():
            pidget.setEnabled(not read_only)

    def _update_subsweep_config_aspect(self, aspect: str, value: Any) -> None:
        if self._subsweep_config is None:
            raise TypeError("SubsweepConfig is None")

        try:
            setattr(self._subsweep_config, aspect, value)
        except Exception as e:
            self._erroneous_aspects.add(aspect)
            self._subsweep_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            if aspect in self._erroneous_aspects:
                self._erroneous_aspects.remove(aspect)

        self._broadcast()

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        for aspect, pidget in self._subsweep_config_pidgets.items():
            if aspect not in self._erroneous_aspects:
                pidget.set_note_text("")

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        return unhandled_results

    def _handle_validation_result(self, result: a121.ValidationResult) -> bool:
        if result.aspect is None or self._subsweep_config is None:
            return False

        if result.aspect in self._erroneous_aspects:
            # If there is an erroneous aspect in the GUI, we do not want to overwrite that.
            # Once the erroneous aspect is handled with, the same validation result will
            # come through here anyway
            return True

        result_handled = False

        if result.source == self._subsweep_config:
            self._subsweep_config_pidgets[result.aspect].set_note_text(
                result.message, result.criticality
            )
            result_handled = True

        return result_handled

    def _broadcast(self) -> None:
        self.sig_update.emit(self._subsweep_config)
