# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.a2.model import power as a2_power
from acconeer.exptool.a2.model.power.formatting import (
    format_current,
    profile_columns,
    profile_rows,
)
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    BreakdownToggleEvent,
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)

from ._a2_power_selections import APS_ACTIVE_STATE
from .a2_heatmap_capon_config_input import HeatmapCaponConfigEvent
from .a2_heatmap_coherent_config_input import HeatmapCoherentConfigEvent
from .a2_heatmap_conventional_config_input import HeatmapConventionalConfigEvent
from .a2_heatmap_robust_capon_config_input import HeatmapRobustCaponConfigEvent
from .a2_session_config_input import SessionConfigEvent as A2SessionConfigEvent


class _A2StateData(t.NamedTuple):
    session_config: t.Any
    aps_sleep_state: t.Any
    aps_idle_state: t.Any
    algorithm: a2_power.algo.Algorithm
    temperature: int


def make_profile_table(
    profile: a2_power.CompositeRegion,
    show_components: bool = False,
) -> QTableWidget:
    """Build a non-editable QTableWidget rendering of a power profile.

    The Qt counterpart of ``a2_power.formatting.render_profile()``,
    which produces an ASCII rendering. Both consume the same row data
    via ``a2_power.formatting.profile_rows()``.
    """
    columns = profile_columns(profile, show_components)
    rows = profile_rows(profile, show_components)
    table = QTableWidget(len(rows), len(columns))
    table.setHorizontalHeaderLabels(list(columns))
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            item = QTableWidgetItem(value)
            if c > 0:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, c, item)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for c in range(1, len(columns)):
        header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

    table.resizeRowsToContents()
    row_height = table.verticalHeader().sectionSize(0) if len(rows) > 0 else 0
    table.setFixedHeight(table.horizontalHeader().height() + row_height * len(rows) + 2)
    return table


class PowerStateSummaryOutput(QScrollArea):
    INTERESTS: t.ClassVar[set[type]] = {
        A2SessionConfigEvent,
        HeatmapCaponConfigEvent,
        HeatmapCoherentConfigEvent,
        HeatmapConventionalConfigEvent,
        HeatmapRobustCaponConfigEvent,
        IdentifiedServiceUninstalledEvent,
        ChangeIdEvent,
        BreakdownToggleEvent,
    }
    description: t.ClassVar[str] = (
        "Shows per-state duration, average current, energy and optional "
        "current-breakdown for A2 configurations."
    )
    window_title = "A2 State summary"

    def __init__(self, broker: EventBroker) -> None:
        super().__init__()

        self._entries: dict[str, _A2StateData] = {}
        self._show_breakdown = True

        self._content = QWidget()
        self._layout = QVBoxLayout(self._content)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._placeholder = QLabel("Nothing to show (add an A2 configuration)")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._placeholder)

        self.setWidget(self._content)
        self.setWidgetResizable(True)

        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)
        broker.brief_service(self)

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, A2SessionConfigEvent):
            self._handle_a2_session_config_event(event)
        elif isinstance(event, HeatmapCaponConfigEvent):
            self._handle_a2_capon_heatmap_config_event(event)
        elif isinstance(event, HeatmapCoherentConfigEvent):
            self._handle_a2_coherent_heatmap_config_event(event)
        elif isinstance(event, HeatmapConventionalConfigEvent):
            self._handle_a2_conventional_heatmap_config_event(event)
        elif isinstance(event, HeatmapRobustCaponConfigEvent):
            self._handle_a2_robust_capon_heatmap_config_event(event)
        elif isinstance(event, IdentifiedServiceUninstalledEvent):
            self._handle_identified_service_uninstalled_event(event)
        elif isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        elif isinstance(event, BreakdownToggleEvent):
            self._show_breakdown = event.enabled
            self._render()
        else:
            raise NotImplementedError

    def _handle_a2_session_config_event(self, event: A2SessionConfigEvent) -> None:
        self._entries[event.service_id] = _A2StateData(
            event.session_config,
            event.aps_sleep_state,
            event.aps_idle_state,
            a2_power.algo.SparseIq(),
            event.temperature,
        )
        self._render()

    def _handle_a2_capon_heatmap_config_event(self, event: HeatmapCaponConfigEvent) -> None:
        self._entries[event.service_id] = _A2StateData(
            event.session_config,
            event.aps_sleep_state,
            event.aps_idle_state,
            a2_power.algo.HeatmapCapon.create(event.heatmap_config),
            event.temperature,
        )
        self._render()

    def _handle_a2_coherent_heatmap_config_event(self, event: HeatmapCoherentConfigEvent) -> None:
        self._entries[event.service_id] = _A2StateData(
            event.session_config,
            event.aps_sleep_state,
            event.aps_idle_state,
            a2_power.algo.HeatmapCoherent.create(event.heatmap_config),
            event.temperature,
        )
        self._render()

    def _handle_a2_conventional_heatmap_config_event(
        self, event: HeatmapConventionalConfigEvent
    ) -> None:
        self._entries[event.service_id] = _A2StateData(
            event.session_config,
            event.aps_sleep_state,
            event.aps_idle_state,
            a2_power.algo.HeatmapConventional.create(event.heatmap_config),
            event.temperature,
        )
        self._render()

    def _handle_a2_robust_capon_heatmap_config_event(
        self, event: HeatmapRobustCaponConfigEvent
    ) -> None:
        self._entries[event.service_id] = _A2StateData(
            event.session_config,
            event.aps_sleep_state,
            event.aps_idle_state,
            a2_power.algo.HeatmapRobustCapon.create(event.heatmap_config),
            event.temperature,
        )
        self._render()

    def _handle_identified_service_uninstalled_event(
        self, event: IdentifiedServiceUninstalledEvent
    ) -> None:
        self._entries.pop(event.id_, None)
        self._render()

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        entry = self._entries.pop(event.old_id, None)
        if entry is not None:
            self._entries[event.new_id] = entry
        self._render()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

    def _render(self) -> None:
        self._clear_layout()

        if not self._entries:
            self._placeholder = QLabel("Nothing to show (add an A2 configuration)")
            self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(self._placeholder)
            return

        for service_id, data in self._entries.items():
            sensor = a2_power.Sensor.at_temperature(data.temperature)
            has_split = sensor.get_sensor_data().has_current_breakdown
            show_components = self._show_breakdown and has_split

            converged = a2_power.converged_session(
                data.session_config,
                aps_sleep_state=data.aps_sleep_state,
                aps_idle_state=data.aps_idle_state,
                aps_active_state=APS_ACTIVE_STATE,
                absolute_tolerance=0.01e-3,
                algorithm=data.algorithm,
                sensor=sensor,
            )
            single_active = a2_power.active_frame(
                data.session_config,
                aps_sleep_state=data.aps_sleep_state,
                aps_idle_state=data.aps_idle_state,
                aps_active_state=APS_ACTIVE_STATE,
                algorithm=data.algorithm,
                sensor=sensor,
            )

            temp_part = f"Temperature: {data.temperature} °C  ·  " if has_split else ""
            heading = QLabel(
                f"<b>[{service_id}]</b>  "
                f"{temp_part}"
                f"Converged avg current: {format_current(converged.average_current)}"
            )
            self._layout.addWidget(heading)

            self._layout.addWidget(QLabel("Converged average"))
            self._layout.addWidget(make_profile_table(converged, show_components))
            self._layout.addWidget(QLabel("Single active frame"))
            self._layout.addWidget(make_profile_table(single_active, show_components))

            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Sunken)
            self._layout.addWidget(separator)

        # Push the entry widgets to the top of the scroll area so they
        # don't get stretched when there's empty space below.
        self._layout.addStretch()
