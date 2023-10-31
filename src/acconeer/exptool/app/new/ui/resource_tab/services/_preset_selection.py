# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtWidgets import QPushButton, QVBoxLayout

from acconeer.exptool.app.new.ui.components import GroupBox


def create_plugin_selection_widget(
    title: str, *rows: t.Tuple[str, t.Iterable[t.Callable[[], t.Any]]]
) -> GroupBox[QVBoxLayout]:
    widget = GroupBox.vertical(left_header=title)

    widget.setStyleSheet("QPushButton { text-align: left; font-weight: bold; }")
    for button_label, on_clicks in rows:
        button = QPushButton(button_label)
        for on_click in on_clicks:
            button.clicked.connect(on_click)
        widget.layout().addWidget(button)

    return widget
