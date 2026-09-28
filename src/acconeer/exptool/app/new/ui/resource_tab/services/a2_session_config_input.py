# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs

from PySide6.QtWidgets import QVBoxLayout

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import (
    ValidationResult,
)
from acconeer.exptool.a2.model import power
from acconeer.exptool.app.new.ui.components.a2 import SessionConfigEditor
from acconeer.exptool.app.new.ui.resource_tab.event_system import ChangeIdEvent, EventBroker
from acconeer.exptool.app.new.ui.utils import LayoutWrapper, ScrollAreaDecorator, TopAlignDecorator

from ._a2_power_selections import ApsSleepState, PowerSelectionsEditor


@attrs.frozen
class SessionConfigEvent:
    service_id: str
    session_config: a2.SessionConfig
    aps_sleep_state: ApsSleepState
    aps_idle_state: power.SensorConstants.ApsIdleState
    # Temperature in °C; must be one of the values present in the YAML's
    # ``temperatures:`` section, or 25 as the fallback when there is none.
    temperature: int = 25


class SessionConfigInput(ScrollAreaDecorator):
    INTERESTS: t.ClassVar[set[type]] = {ChangeIdEvent}
    description: t.ClassVar[str] = (
        "Specify sensor configuration as in the Stream tab.\n\n"
        + "Additionally, you can specify a lower idle state."
    )
    id_: str = ""

    def __init__(self, broker: EventBroker, initial_config: a2.SessionConfig) -> None:
        layout = QVBoxLayout()
        super().__init__(TopAlignDecorator(LayoutWrapper(layout)))
        self.setMinimumWidth(200)

        self._broker = broker

        self.power_selections = PowerSelectionsEditor(self)
        self.power_selections.sig_update.connect(self._offer_event_if_config_is_valid)

        self.editor = SessionConfigEditor()
        self.editor.set_data(initial_config)
        self.editor.sig_update.connect(self.editor.set_data)
        self.editor.sig_update.connect(self._display_validation_results)
        self.editor.sig_update.connect(self._offer_event_if_config_is_valid)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.power_selections)
        layout.addWidget(self.editor)

        self.id_ = broker.install_identified_service(self, "a2-sparse-iq")
        self.uninstall_function = lambda: broker.uninstall_identified_service(self, self.id_)
        self._offer_event_if_config_is_valid()
        self.window_title = f"<b><code>[{self.id_}]</code></b> A2 Sparse IQ config"
        self.fixed_title = "A2 Sparse IQ config"

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
        except ValidationResult:
            return

        self._broker.offer_event(
            SessionConfigEvent(self.id_, config, *self.power_selections.get_data())
        )

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        else:
            raise NotImplementedError

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        if event.old_id == self.id_:
            self.id_ = event.new_id
