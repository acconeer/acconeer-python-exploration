# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6 import QtCore
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class CollapsibleWidget(QWidget):
    def __init__(self, label: str, widget: QWidget, parent: t.Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.widget = widget
        self.widget.setVisible(False)

        self.arrow_button = QToolButton()
        self.arrow_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.arrow_button.setText(label)
        self.arrow_button.setArrowType(QtCore.Qt.RightArrow)
        self.arrow_button.setCheckable(True)
        self.arrow_button.setChecked(False)
        self.arrow_button.toggled.connect(self._on_toggle)

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.arrow_button)
        self.layout().addWidget(self.widget)

    def set_collapsed(self, collapsed: bool) -> None:
        self.widget.setVisible(not collapsed)
        self.arrow_button.setArrowType(QtCore.Qt.RightArrow if collapsed else QtCore.Qt.DownArrow)

    def _on_toggle(self, checked: bool) -> None:
        self.set_collapsed(not checked)
