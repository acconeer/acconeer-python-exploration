from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget


class VerticalGroupBox(QGroupBox):
    def __init__(self, title: str, parent: Optional[QWidget]) -> None:
        super().__init__(parent=parent)
        self.setTitle(title)
        self.setLayout(QVBoxLayout(parent=self))
