# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved
from __future__ import annotations

from typing import Optional

from PySide6 import QtCore
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QScrollArea, QVBoxLayout, QWidget


class ScrollAreaDecorator(QScrollArea):
    def __init__(self, decoratee: QWidget) -> None:
        """Puts `decoratee` in a frameless QScrollArea with no horizontal scroll."""
        super().__init__()

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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


class LeftAlignDecorator(QWidget):
    def __init__(self, decoratee: QWidget) -> None:
        """Left-aligns `decoratee` by using QHBoxLayout and its stretch-functionality"""
        super().__init__()

        layout = QHBoxLayout(self)
        self.setLayout(layout)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(decoratee)
        layout.addStretch(1)


class LayoutWrapper(QWidget):
    def __init__(self, wrappee: QLayout) -> None:
        super().__init__()
        self.setLayout(wrappee)


class HorizontalSeparator(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
