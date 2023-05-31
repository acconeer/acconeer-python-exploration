# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from typing import Optional, Type

from PySide6.QtWidgets import QGridLayout, QGroupBox, QLayout, QVBoxLayout, QWidget


class GroupBox(QGroupBox):
    def __init__(
        self, title: str, layout_type: Type[QLayout], *, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)
        self.setTitle(title)
        self.setLayout(layout_type())

    @classmethod
    def vertical(cls, title: str, *, parent: Optional[QWidget] = None) -> GroupBox:
        return cls(title, QVBoxLayout, parent=parent)

    @classmethod
    def grid(cls, title: str, *, parent: Optional[QWidget] = None) -> GroupBox:
        return cls(title, QGridLayout, parent=parent)
