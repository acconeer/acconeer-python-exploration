# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool.a2.model import power
from acconeer.exptool.app.new.ui.components import GroupBox, pidgets


ApsSleepState = t.Union[power.SensorConstants.ApsSleepState, power.SensorConstants.ApsIdleState]

PowerSelections = t.Tuple[
    ApsSleepState,
    power.SensorConstants.ApsIdleState,
    int,
]

# Processing always runs with APS at high frequency.
APS_ACTIVE_STATE = power.SensorConstants.ApsActiveState.APS_HF


class PowerSelectionsEditor(QWidget):
    """The sensor states and temperature the power model is evaluated at

    Every A2 input offers the same ones, so they live here rather than in each
    of them.
    """

    sig_update = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.aps_sleep_state_selection = pidgets.ComboboxPidgetFactory[ApsSleepState](
            name_label_text="APS Sleep State, RS OFF:",
            name_label_tooltip="The lowest sleep state of the sensor between frames. RS is off. Only applicable if update rate is set.",
            items=[
                ("HF WFI", power.SensorConstants.ApsIdleState.APS_HF_WFI),
                ("MF WFI", power.SensorConstants.ApsIdleState.APS_MF_WFI),
                ("LF WFI", power.SensorConstants.ApsIdleState.APS_LF_WFI),
                ("Shallow", power.SensorConstants.ApsSleepState.SHALLOW_SLEEP),
                ("Deep", power.SensorConstants.ApsSleepState.DEEP_SLEEP),
                ("Ultra Deep", power.SensorConstants.ApsSleepState.ULTRA_DEEP_SLEEP),
            ],
        ).create(self)
        self.aps_idle_state_selection = pidgets.ComboboxPidgetFactory[
            power.SensorConstants.ApsIdleState
        ](
            name_label_text="APS Idle State:",
            name_label_tooltip="The idle state of APS while RS is active",
            items=[
                ("HF WFI", power.SensorConstants.ApsIdleState.APS_HF_WFI),
                ("MF WFI", power.SensorConstants.ApsIdleState.APS_MF_WFI),
                ("LF WFI", power.SensorConstants.ApsIdleState.APS_LF_WFI),
            ],
        ).create(self)

        available_temperatures = power.SensorConstants.default().available_temperatures or (25,)
        self.temperature_selection = pidgets.ComboboxPidgetFactory[int](
            name_label_text="Temperature:",
            name_label_tooltip=("Ambient temperature for power estimation"),
            items=[(f"{tc} °C", tc) for tc in available_temperatures],
        ).create(self)
        default_temperature = 25 if 25 in available_temperatures else available_temperatures[0]

        self.aps_sleep_state_selection.set_data(power.SensorConstants.ApsSleepState.SHALLOW_SLEEP)
        self.aps_idle_state_selection.set_data(power.SensorConstants.ApsIdleState.APS_HF_WFI)
        self.temperature_selection.set_data(default_temperature)

        for selection in (
            self.aps_sleep_state_selection,
            self.aps_idle_state_selection,
            self.temperature_selection,
        ):
            # The pidgets carry the new value; this signal only says something changed.
            selection.sig_update.connect(lambda _: self.sig_update.emit())

        wrapped_temperature_selection = self._wrap(self.temperature_selection)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._wrap(self.aps_sleep_state_selection))
        layout.addWidget(self._wrap(self.aps_idle_state_selection))
        layout.addWidget(wrapped_temperature_selection)
        self.setLayout(layout)

        wrapped_temperature_selection.setVisible(
            len(power.SensorConstants.default().available_temperatures) > 1
        )

    @staticmethod
    def _wrap(selection: QWidget) -> GroupBox[QVBoxLayout]:
        wrapper = GroupBox.vertical(left_header="")
        wrapper.layout().addWidget(selection)

        return wrapper

    def get_data(self) -> PowerSelections:
        return (
            self.aps_sleep_state_selection.get_data(),
            self.aps_idle_state_selection.get_data(),
            self.temperature_selection.get_data(),
        )
