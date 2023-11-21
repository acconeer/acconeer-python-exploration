# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t

import attrs

from PySide6.QtWidgets import QVBoxLayout

from acconeer.exptool import a121
from acconeer.exptool.a121.algo.distance._configs import get_high_accuracy_detector_config
from acconeer.exptool.a121.algo.distance._detector import Detector, DetectorConfig
from acconeer.exptool.a121.algo.distance._pidget_mapping import get_pidget_mapping
from acconeer.exptool.a121.model import power
from acconeer.exptool.app.new.ui.components import AttrsConfigEditor, GroupBox, pidgets
from acconeer.exptool.app.new.ui.resource_tab.event_system import EventBroker
from acconeer.exptool.app.new.ui.utils import LayoutWrapper, ScrollAreaDecorator, TopAlignDecorator

from ._preset_selection import create_plugin_selection_widget


@attrs.frozen
class DistanceConfigEvent:
    service_id: str
    config: DetectorConfig
    lower_power_state: t.Optional[power.Sensor.LowerPowerState]

    @property
    def translated_session_config(self) -> a121.SessionConfig:
        (session_config, _) = Detector._detector_to_session_config_and_processor_specs(
            self.config,
            sensor_ids=[1],
        )
        return session_config


class DistanceConfigInput(ScrollAreaDecorator):
    INTERESTS: t.ClassVar[set[type]] = set()
    description: t.ClassVar[str] = (
        "Specify distance configuration as in the Stream tab.\n\n"
        + "Additionally, you can specify a lower power state."
    )

    def __init__(self, broker: EventBroker, initial_config: DetectorConfig) -> None:
        layout = QVBoxLayout()
        super().__init__(TopAlignDecorator(LayoutWrapper(layout)))

        self.setMinimumWidth(400)

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
        ).create(self)

        self.power_state_selection.set_data(None)
        self.power_state_selection.sig_update.connect(self._offer_event_if_config_is_valid)

        self.editor = AttrsConfigEditor(
            title="Distance config",
            factory_mapping=get_pidget_mapping(),
            config_type=DetectorConfig,
        )
        self.editor.set_data(initial_config)
        self.editor.sig_update.connect(self.editor.set_data)
        self.editor.sig_update.connect(self._display_validation_results)
        self.editor.sig_update.connect(self._offer_event_if_config_is_valid)

        wrapped_power_state_selection = GroupBox.vertical(left_header="")
        wrapped_power_state_selection.layout().addWidget(self.power_state_selection)

        preset_selection = create_plugin_selection_widget(
            "Presets",
            (
                "Balanced",
                [
                    lambda: self.editor.set_data(DetectorConfig()),
                    self._offer_event_if_config_is_valid,
                ],
            ),
            (
                "High accuracy",
                [
                    lambda: self.editor.set_data(get_high_accuracy_detector_config()),
                    self._offer_event_if_config_is_valid,
                ],
            ),
        )

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(wrapped_power_state_selection)
        layout.addWidget(self.editor)
        layout.addWidget(preset_selection)

        (self.uninstall_function, self._id) = broker.install_identified_service(self, "distance")
        self._offer_event_if_config_is_valid()
        self.window_title = f"<b><code>[{self._id}]</code></b> Distance config"

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
            DistanceConfigEvent(
                self._id,
                config,
                self.power_state_selection.get_data(),
            )
        )

    def handle_event(self, event: t.Any) -> None:
        pass
