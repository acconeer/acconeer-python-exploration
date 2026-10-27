# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

import attrs

from PySide6.QtWidgets import QBoxLayout, QVBoxLayout

from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import (
    ValidationResult,
)
from acconeer.exptool.a2.algo.heatmap.config_common import (
    HeatmapAndSessionConfigCommon,
    HeatmapConfigCommon,
)
from acconeer.exptool.a2.model import power
from acconeer.exptool.app.new.ui.components import AttrsConfigEditor, MiscErrorView
from acconeer.exptool.app.new.ui.components.a2 import SessionConfigEditor
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping
from acconeer.exptool.app.new.ui.resource_tab.event_system import ChangeIdEvent, EventBroker
from acconeer.exptool.app.new.ui.utils import LayoutWrapper, ScrollAreaDecorator, TopAlignDecorator

from ._a2_power_selections import ApsSleepState, PowerSelections, PowerSelectionsEditor


_HeatmapConfigT = t.TypeVar("_HeatmapConfigT", bound=HeatmapConfigCommon)
_EventT = t.TypeVar("_EventT")


@attrs.frozen
class HeatmapConfigEvent(t.Generic[_HeatmapConfigT]):
    service_id: str
    session_config: a2.SessionConfig
    heatmap_config: _HeatmapConfigT


@attrs.frozen
class HeatmapPowerConfigEvent(HeatmapConfigEvent[_HeatmapConfigT]):
    aps_sleep_state: ApsSleepState
    aps_idle_state: power.SensorConstants.ApsIdleState
    # Temperature in °C; must be one of the values present in the YAML's
    # ``temperatures:`` section, or 25 as the fallback when there is none.
    temperature: int = 25


class HeatmapConfigInput(ScrollAreaDecorator, t.Generic[_HeatmapConfigT, _EventT]):
    """Resource Calculator input for one of the heatmap processors

    Subclasses parametrize the editors and build the event, which is what the
    outputs dispatch on.
    """

    INTERESTS: t.ClassVar[set[type]] = set([ChangeIdEvent])
    description: t.ClassVar[str] = "Specify sensor configuration as in the Stream tab."
    id_: str = ""

    def __init__(
        self,
        broker: EventBroker,
        initial_config: HeatmapAndSessionConfigCommon[_HeatmapConfigT],
        *,
        config_type: t.Type[_HeatmapConfigT],
        pidget_mapping: PidgetFactoryMapping,
        id_prefix: str,
        title: str,
    ) -> None:
        layout = QVBoxLayout()
        super().__init__(TopAlignDecorator(LayoutWrapper(layout)))
        self.setMinimumWidth(200)

        self._broker = broker

        layout.setContentsMargins(0, 0, 0, 0)

        self.heatmap_config_editor = AttrsConfigEditor(
            title="Heatmap config",
            factory_mapping=pidget_mapping,
            config_type=config_type,
        )
        self.heatmap_config_editor.set_data(initial_config.heatmap_config)
        self.heatmap_config_editor.sig_update.connect(self.heatmap_config_editor.set_data)
        self.heatmap_config_editor.sig_update.connect(self._display_validation_results)
        self.heatmap_config_editor.sig_update.connect(self._offer_event_if_config_is_valid)

        self.session_config_editor = SessionConfigEditor(single_subsweep=True)
        self.session_config_editor.set_data(initial_config.session_config)
        self.session_config_editor.sig_update.connect(self.session_config_editor.set_data)
        self.session_config_editor.sig_update.connect(self._display_validation_results)
        self.session_config_editor.sig_update.connect(self._offer_event_if_config_is_valid)

        self.misc_error_view = MiscErrorView(self)

        layout.addWidget(self.misc_error_view)
        self._add_extra_widgets(layout)
        layout.addWidget(self.heatmap_config_editor)
        layout.addWidget(self.session_config_editor)

        self.id_ = broker.install_identified_service(self, id_prefix)
        self.uninstall_function = lambda: broker.uninstall_identified_service(self, self.id_)
        self._offer_event_if_config_is_valid()
        self.window_title = f"<b><code>[{self.id_}]</code></b> {title}"
        self.fixed_title = title

    def _add_extra_widgets(self, layout: QBoxLayout) -> None:
        """Adds the widgets that go above the config editors"""

    def _create_event(
        self, session_config: a2.SessionConfig, heatmap_config: _HeatmapConfigT
    ) -> _EventT:
        raise NotImplementedError

    def _display_validation_results(self) -> None:
        session_config = self.session_config_editor.get_data()
        heatmap_config = self.heatmap_config_editor.get_data()

        if heatmap_config is None or session_config is None:
            return

        results = session_config._collect_validation_results()
        results += heatmap_config._collect_validation_results(session_config)

        not_handled = self.session_config_editor.handle_validation_results(results)
        not_handled = self.heatmap_config_editor.handle_validation_results(not_handled)
        self.misc_error_view.handle_validation_results(not_handled)

    def _offer_event_if_config_is_valid(self) -> None:
        if not (self.session_config_editor.is_ready and self.heatmap_config_editor.is_ready):
            return

        session_config = self.session_config_editor.get_data()
        heatmap_config = self.heatmap_config_editor.get_data()

        if heatmap_config is None or session_config is None:
            return

        try:
            heatmap_config.validate(session_config)
        except ValidationResult:
            return

        self._broker.offer_event(self._create_event(session_config, heatmap_config))

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        else:
            raise NotImplementedError

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        if event.old_id == self.id_:
            self.id_ = event.new_id


class HeatmapPowerConfigInput(HeatmapConfigInput[_HeatmapConfigT, _EventT]):
    """Input for a heatmap processor that the power outputs also estimate"""

    description: t.ClassVar[str] = (
        "Specify sensor configuration as in the Stream tab.\n\n"
        + "Additionally, you can specify a lower idle state."
    )

    def _add_extra_widgets(self, layout: QBoxLayout) -> None:
        self.power_selections = PowerSelectionsEditor(self)
        self.power_selections.sig_update.connect(self._offer_event_if_config_is_valid)

        layout.addWidget(self.power_selections)

    def _power_selections(self) -> PowerSelections:
        return self.power_selections.get_data()
