# Copyright (c) Acconeer AB, 2022
# All rights reserved
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget


class ScrollAreaDecorator(QScrollArea):
    def __init__(self, decoratee: QWidget) -> None:
        """Puts `decoratee` in a frameless QScrollArea with no horizontal scroll."""
        super().__init__()

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.horizontalScrollBar().setEnabled(False)

        self.setWidget(decoratee)


class TopAlignDecorator(QWidget):
    def __init__(self, decoratee: QWidget) -> None:
        """Top-aligns `decoratee` by using QVBoxLayout and its stretch-functionality"""
        super().__init__()

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(decoratee)
        layout.addStretch(1)


class HorizontalSeparator(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.HLine)
