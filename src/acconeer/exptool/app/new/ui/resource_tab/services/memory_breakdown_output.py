# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import itertools
import typing as t

from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QTextEdit

from acconeer.exptool.a121.model import memory
from acconeer.exptool.app.new.ui.resource_tab.event_system import (
    ChangeIdEvent,
    EventBroker,
    IdentifiedServiceUninstalledEvent,
)

from .distance_config_input import DistanceConfigEvent
from .presence_config_input import PresenceConfigEvent
from .session_config_input import SessionConfigEvent


class MemoryBreakdownOutput(QTextEdit):
    INTERESTS: t.ClassVar[set[type]] = {
        DistanceConfigEvent,
        SessionConfigEvent,
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
        if isinstance(event, SessionConfigEvent):
            self._handle_session_config_event(event)
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

    def _handle_session_config_event(self, event: SessionConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            memory.session_rss_heap_memory(event.session_config),
            memory.session_external_heap_memory(event.session_config),
        )

        self._show_memory_numbers()

    def _handle_distance_config_event(self, event: DistanceConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            memory.distance_rss_heap_memory(event.config),
            memory.distance_external_heap_memory(event.config),
        )

        self._show_memory_numbers()

    def _handle_presence_config_event(self, event: PresenceConfigEvent) -> None:
        self._memory_numbers[event.service_id] = (
            memory.presence_rss_heap_memory(event.config),
            memory.presence_external_heap_memory(event.config),
        )

        self._show_memory_numbers()

    def _handle_identified_service_uninstalled_event(
        self, event: IdentifiedServiceUninstalledEvent
    ) -> None:
        self._memory_numbers.pop(event.id_)
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
        if not self._memory_numbers:
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
