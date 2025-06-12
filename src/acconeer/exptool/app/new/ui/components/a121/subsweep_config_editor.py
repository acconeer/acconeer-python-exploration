# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import logging
from functools import partial
from typing import Any, Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool._core.entities.validation_result import Criticality
from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.app.new.ui.components import pidgets
from acconeer.exptool.app.new.ui.components.a121 import RangeHelpView
from acconeer.exptool.app.new.ui.components.collapsible_widget import CollapsibleWidget
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping


log = logging.getLogger(__name__)


class SubsweepConfigEditor(DataEditor[Optional[a121.SubsweepConfig]]):
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
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "start_point"),
        ),
        "num_points": pidgets.IntPidgetFactory(
            name_label_text="Number of points:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "num_points"),
            limits=(1, 4095),
        ),
        "step_length": pidgets.IntPidgetFactory(
            name_label_text="Step length:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "step_length"),
            limits=(1, None),
        ),
        "hwaas": pidgets.IntPidgetFactory(
            name_label_text="HWAAS:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "hwaas"),
            limits=(1, 511),
        ),
        "receiver_gain": pidgets.IntPidgetFactory(
            name_label_text="Receiver gain:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "receiver_gain"),
            limits=(0, 23),
        ),
        "profile": pidgets.EnumPidgetFactory(
            enum_type=a121.Profile,
            name_label_text="Profile:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "profile"),
            label_mapping=PROFILE_LABEL_MAP,
        ),
        "prf": pidgets.EnumPidgetFactory(
            enum_type=a121.PRF,
            name_label_text="PRF:",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "prf"),
            label_mapping=PRF_LABEL_MAP,
        ),
        "enable_tx": pidgets.CheckboxPidgetFactory(
            name_label_text="Enable transmitter",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "enable_tx"),
        ),
        "enable_loopback": pidgets.CheckboxPidgetFactory(
            name_label_text="Enable loopback",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "enable_loopback"),
        ),
        "phase_enhancement": pidgets.CheckboxPidgetFactory(
            name_label_text="Phase enhancement",
            name_label_tooltip=get_attribute_docstring(a121.SubsweepConfig, "phase_enhancement"),
        ),
        "iq_imbalance_compensation": pidgets.CheckboxPidgetFactory(
            name_label_text="IQ imbalance compensation",
            name_label_tooltip=get_attribute_docstring(
                a121.SubsweepConfig, "iq_imbalance_compensation"
            ),
        ),
    }
    ADVANCED_PARAMETERS = {
        "receiver_gain",
        "prf",
        "enable_tx",
        "enable_loopback",
        "phase_enhancement",
        "iq_imbalance_compensation",
    }

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)

        self._subsweep_config_pidgets = {}
        self._erroneous_aspects = set()

        self._subsweep_config = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.range_help_view = RangeHelpView(self)
        layout.addWidget(self.range_help_view)

        collapsible_layout = QVBoxLayout()

        for aspect, factory in self.SUBSWEEP_CONFIG_FACTORIES.items():
            pidget = factory.create(self)

            if aspect in self.ADVANCED_PARAMETERS:
                collapsible_layout.addWidget(pidget)
            else:
                layout.addWidget(pidget)

            pidget.sig_update.connect(partial(self._update_subsweep_config_aspect, aspect))

            self._subsweep_config_pidgets[aspect] = pidget

        # Some left margin here will show the hierarchy
        collapsible_layout.setContentsMargins(11, 0, 0, 0)
        dummy = QWidget()
        dummy.setLayout(collapsible_layout)
        self.collapsible_widget = CollapsibleWidget(label="Advanced", widget=dummy)

        layout.addWidget(self.collapsible_widget)

        self.setLayout(layout)

    def set_read_only(self, read_only: bool) -> None:
        for pidget in self._subsweep_config_pidgets.values():
            pidget.setEnabled(not read_only)

    def set_data(self, subsweep_config: Optional[a121.SubsweepConfig]) -> None:
        if self._subsweep_config == subsweep_config:
            return

        self.range_help_view.set_data(subsweep_config)
        self._subsweep_config = subsweep_config

        self.setEnabled(self._subsweep_config is not None)
        if self._subsweep_config is None:
            log.debug("could not update ui as SubsweepConfig is None")
            return

        for aspect, pidget in self._subsweep_config_pidgets.items():
            if aspect in self._erroneous_aspects:
                continue
            pidget.set_data(getattr(self._subsweep_config, aspect))

    def get_data(self) -> Optional[a121.SubsweepConfig]:
        return copy.deepcopy(self._subsweep_config)

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        current_data = self.get_data()
        advanced_results = [
            r
            for r in results
            if (r.aspect in self.ADVANCED_PARAMETERS) and (r.source == current_data)
        ]

        if any(result.criticality is Criticality.ERROR for result in advanced_results):
            self.collapsible_widget.set_icon(icons.WARNING(color=icons.ERROR_RED))
        elif any(result.criticality is Criticality.WARNING for result in advanced_results):
            self.collapsible_widget.set_icon(icons.WARNING())
        else:
            self.collapsible_widget.set_icon(None)

        for aspect, pidget in self._subsweep_config_pidgets.items():
            if aspect not in self._erroneous_aspects:
                pidget.set_note_text("")

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        return unhandled_results

    @property
    def is_ready(self) -> bool:
        return self._erroneous_aspects == set()

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

    def _update_subsweep_config_aspect(self, aspect: str, value: Any) -> None:
        if self._subsweep_config is None:
            msg = "SubsweepConfig is None"
            raise TypeError(msg)

        config = copy.deepcopy(self._subsweep_config)

        try:
            setattr(config, aspect, value)
        except Exception as e:
            self._erroneous_aspects.add(aspect)
            self._subsweep_config_pidgets[aspect].set_note_text(e.args[0], Criticality.ERROR)

            # this emit needs to be done to signal that "is_ready" has changed.
            self.sig_update.emit(self.get_data())
        else:
            self._erroneous_aspects.discard(aspect)
            self.set_data(config)
            self.sig_update.emit(config)
