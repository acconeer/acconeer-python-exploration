# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import itertools
import typing as t

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QTextEdit

from acconeer.exptool.a2.model import memory as a2_memory
from acconeer.exptool.a121.model import memory as a121_memory
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)

from .a2_heatmap_capon_config_input import HeatmapCaponConfigEvent
from .a2_heatmap_coherent_config_input import HeatmapCoherentConfigEvent
from .a2_heatmap_conventional_config_input import HeatmapConventionalConfigEvent
from .a2_heatmap_robust_capon_config_input import HeatmapRobustCaponConfigEvent
from .a2_session_config_input import SessionConfigEvent as A2SessionConfigEvent
from .a121_session_config_input import SessionConfigEvent as A121SessionConfigEvent
from .distance_config_input import DistanceConfigEvent
from .presence_config_input import PresenceConfigEvent


class MemoryBreakdownOutput(QTextEdit):
    INTERESTS: t.ClassVar[set[type]] = {
        DistanceConfigEvent,
        A121SessionConfigEvent,
        A2SessionConfigEvent,
        HeatmapCaponConfigEvent,
        HeatmapCoherentConfigEvent,
        HeatmapConventionalConfigEvent,
        HeatmapRobustCaponConfigEvent,
        PresenceConfigEvent,
        IdentifiedServiceUninstalledEvent,
        ChangeIdEvent,
    }
    description: t.ClassVar[str] = "Tabulates heap memory consumption of configurations"
    window_title = "Memory breakdown"

    def __init__(self, broker: EventBroker) -> None:
        super().__init__()

        self._memory_numbers: dict[str, tuple[int, int]] = {}

        self.setPlaceholderText("Nothing to show")
        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setFontFamily("monospace")

        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)
        broker.brief_service(self)

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, A121SessionConfigEvent):
            self._handle_a121_session_config_event(event)
        elif isinstance(event, A2SessionConfigEvent):
            self._handle_a2_session_config_event(event)
        elif isinstance(event, HeatmapCaponConfigEvent):
            self._handle_a2_capon_heatmap_config_event(event)
        elif isinstance(event, HeatmapCoherentConfigEvent):
            self._handle_a2_coherent_heatmap_config_event(event)
        elif isinstance(event, HeatmapConventionalConfigEvent):
            self._handle_a2_conventional_heatmap_config_event(event)
        elif isinstance(event, HeatmapRobustCaponConfigEvent):
            self._handle_a2_robust_capon_heatmap_config_event(event)
        elif isinstance(event, DistanceConfigEvent):
            self._handle_distance_config_event(event)
        elif isinstance(event, PresenceConfigEvent):
            self._handle_presence_config_event(event)
        elif isinstance(event, IdentifiedServiceUninstalledEvent):
            self._handle_identified_service_uninstalled_event(event)
        elif isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        else:
            raise NotImplementedError

    def _handle_a121_session_config_event(self, event: A121SessionConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a121_memory.session_rss_heap_memory(event.session_config),
            a121_memory.session_external_heap_memory(event.session_config),
        )

        self._show_memory_numbers()

    def _handle_a2_session_config_event(self, event: A2SessionConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a2_memory.session_rss_heap_memory(event.session_config),
            a2_memory.session_external_heap_memory(event.session_config),
        )

        self._show_memory_numbers()

    def _handle_a2_capon_heatmap_config_event(self, event: HeatmapCaponConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a2_memory.heatmap_capon_rss_heap_memory(event.session_config),
            a2_memory.heatmap_capon_external_heap_memory(
                event.session_config, event.heatmap_config
            ),
        )

        self._show_memory_numbers()

    def _handle_a2_coherent_heatmap_config_event(self, event: HeatmapCoherentConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a2_memory.heatmap_coherent_rss_heap_memory(event.session_config),
            a2_memory.heatmap_coherent_external_heap_memory(
                event.session_config, event.heatmap_config
            ),
        )

        self._show_memory_numbers()

    def _handle_a2_conventional_heatmap_config_event(
        self, event: HeatmapConventionalConfigEvent
    ) -> None:
        self._memory_numbers[event.service_id] = (
            a2_memory.heatmap_conventional_rss_heap_memory(event.session_config),
            a2_memory.heatmap_conventional_external_heap_memory(
                event.session_config, event.heatmap_config
            ),
        )

        self._show_memory_numbers()

    def _handle_a2_robust_capon_heatmap_config_event(
        self, event: HeatmapRobustCaponConfigEvent
    ) -> None:
        self._memory_numbers[event.service_id] = (
            a2_memory.heatmap_robust_capon_rss_heap_memory(event.session_config),
            a2_memory.heatmap_robust_capon_external_heap_memory(
                event.session_config, event.heatmap_config
            ),
        )

        self._show_memory_numbers()

    def _handle_distance_config_event(self, event: DistanceConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a121_memory.distance_rss_heap_memory(event.config),
            a121_memory.distance_external_heap_memory(event.config),
        )

        self._show_memory_numbers()

    def _handle_presence_config_event(self, event: PresenceConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            a121_memory.presence_rss_heap_memory(event.config),
            a121_memory.presence_external_heap_memory(event.config),
        )

        self._show_memory_numbers()

    def _handle_identified_service_uninstalled_event(
        self, event: IdentifiedServiceUninstalledEvent
    ) -> None:
        self._memory_numbers.pop(event.id_, None)
        self._show_memory_numbers()

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        memory_entry = self._memory_numbers.pop(event.old_id, None)

        if memory_entry is not None:
            self._memory_numbers[event.new_id] = memory_entry

        self._show_memory_numbers()

    @staticmethod
    def _fmt_number(number: int) -> str:
        return str(number + (100 - number % 100)) + "B"

    def _show_memory_numbers(self) -> None:
        if not any(self._memory_numbers.values()):
            self.setText("")
        else:
            longest_key = max(len(key) for key in self._memory_numbers)
            fmt = f"{{: <{longest_key}}} {{: <12}} {{}}"
            header = fmt.format("", "RSS heap", "External heap")

            self.setText(
                "\n".join(
                    itertools.chain(
                        [header, "=" * len(header)],
                        (
                            fmt.format(
                                service_id, self._fmt_number(rss), self._fmt_number(external)
                            )
                            for service_id, (rss, external) in self._memory_numbers.items()
                        ),
                    )
                )
            )
