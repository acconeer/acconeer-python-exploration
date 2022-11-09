# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QGridLayout, QGroupBox, QHBoxLayout, QVBoxLayout, QWidget


class VerticalGroupBox(QGroupBox):
    def __init__(self, title: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent=parent)
        self.setTitle(title)
        self.setLayout(QVBoxLayout(self))


class HorizontalGroupBox(QGroupBox):
    def __init__(self, title: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent=parent)
        self.setTitle(title)
        self.setLayout(QHBoxLayout(self))


class GridGroupBox(QGroupBox):
    def __init__(self, title: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent=parent)
        self.setTitle(title)
        self.setLayout(QGridLayout(self))
