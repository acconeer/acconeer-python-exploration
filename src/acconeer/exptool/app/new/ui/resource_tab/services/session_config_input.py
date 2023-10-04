# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t

import attrs

from PySide6.QtWidgets import QVBoxLayout

from acconeer.exptool import a121
from acconeer.exptool.a121.model import power
from acconeer.exptool.app.new.ui.plugin_components import GroupBox, SessionConfigEditor, pidgets
from acconeer.exptool.app.new.ui.resource_tab.event_system import EventBroker
from acconeer.exptool.app.new.ui.utils import LayoutWrapper, ScrollAreaDecorator, TopAlignDecorator


@attrs.frozen
class SessionConfigEvent:
    service_id: str
    session_config: a121.SessionConfig
    lower_power_state: t.Optional[power.Sensor.LowerPowerState]


class SessionConfigInput(ScrollAreaDecorator):
    INTERESTS: t.ClassVar[set[type]] = set()
    description: t.ClassVar[str] = (
        "Specify sensor configuration as in the Stream tab.\n\n"
        + "Additionally, you can specify a lower power state."
    )

    def __init__(self, broker: EventBroker, initial_config: a121.SessionConfig) -> None:
        layout = QVBoxLayout()
        super().__init__(TopAlignDecorator(LayoutWrapper(layout)))
        self.setMinimumWidth(200)

        self._broker = broker
        self.power_state_selection = pidgets.ComboboxPidgetFactory[
            t.Optional[power.Sensor.LowerPowerState]
        ](
            name_label_text="Lower power state:",
            items=[
                ("Don't use", None),
                ("Hibernate", power.Sensor.PowerState.HIBERNATE),
                ("Off", power.Sensor.PowerState.OFF),
            ],
        ).create(
            self
        )

        self.power_state_selection.set_data(None)
        self.power_state_selection.sig_update.connect(self._offer_event_if_config_is_valid)

        self.editor = SessionConfigEditor(supports_multiple_subsweeps=True)
        self.editor._sensor_ids_editor.hide()
        self.editor.set_data(initial_config)
        self.editor.sig_update.connect(self.editor.set_data)
        self.editor.sig_update.connect(self._display_validation_results)
        self.editor.sig_update.connect(self._offer_event_if_config_is_valid)

        wrapped_power_state_selection = GroupBox.vertical(left_header="")
        wrapped_power_state_selection.layout().addWidget(self.power_state_selection)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(wrapped_power_state_selection)
        layout.addWidget(self.editor)

        (self.uninstall_function, self._id) = broker.install_identified_service(self, "sparse-iq")
        self._offer_event_if_config_is_valid()
        self.window_title = f"<b><code>[{self._id}]</code></b> Sparse IQ config"

    def _display_validation_results(self) -> None:
        config = self.editor.get_data()

        if config is None:
            return

        self.editor.handle_validation_results(config._collect_validation_results())

    def _offer_event_if_config_is_valid(self) -> None:
        if not self.editor.is_ready:
            return

        config = self.editor.get_data()

        if config is None:
            return

        try:
            config.validate()
        except a121.ValidationResult:
            return

        self._broker.offer_event(
            SessionConfigEvent(
                self._id,
                config,
                self.power_state_selection.get_data(),
            )
        )

    def handle_event(self, event: t.Any) -> None:
        pass
