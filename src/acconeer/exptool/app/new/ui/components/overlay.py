# Copyright (c) Acconeer AB, 2024
# All rights reserved

# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget


class Overlay(QWidget):
    """Implements overlaying a number of widgets on top of another widget

    'base' is the background widget and 'overlays' is pairs of
    - 'overlay_widget': The actual widget
    - 'positioner': A function that calculates the position of the widget

    'positioner' is a callable that accepts
    - the '.rect()' of 'base' (left, top, width, height)
    - the '.sizeHint()' of 'overlay_widget' (preffered width, height)
    and returns the new rect (left, top, width, height) of 'overlay_widget' should have
    """

    @staticmethod
    def positioner_top_right(base_rect: QRect, overlay_size: QSize) -> QRect:
        top_left = base_rect.topRight() - QPoint(overlay_size.width() + 7, 0)
        return QRect(top_left, overlay_size)

    def __init__(
        self,
        base: QWidget,
        overlays: list[tuple[QWidget, t.Callable[[QRect, QSize], QRect]]],
        parent: t.Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        self._base = base
        self._overlays = overlays

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._base)
        self.setLayout(layout)

        for widget, _ in self._overlays:
            widget.setParent(self)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        for widget, positioner in self._overlays:
            positioned = positioner(self._base.rect(), widget.sizeHint())
            widget.setGeometry(positioned)
