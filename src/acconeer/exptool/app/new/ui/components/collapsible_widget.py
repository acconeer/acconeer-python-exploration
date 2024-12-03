# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QGridLayout, QLabel, QToolButton, QWidget


class CollapsibleWidget(QWidget):
    _ICON_SIZE = 28

    def __init__(self, label: str, widget: QWidget, parent: t.Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.widget = widget
        self.widget.setVisible(False)

        self.arrow_button = QToolButton()
        self.arrow_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.arrow_button.setText(label)
        self.arrow_button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.arrow_button.setCheckable(True)
        self.arrow_button.setChecked(False)
        self.arrow_button.toggled.connect(self._on_toggle)

        self.icon_label = QLabel()
        self.set_icon(None)

        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.arrow_button, 0, 0)
        layout.addWidget(self.icon_label, 0, 1)
        layout.addWidget(self.widget, 1, 0, 1, -1)

        self.setLayout(layout)

    def set_collapsed(self, collapsed: bool) -> None:
        self.widget.setVisible(not collapsed)
        self.arrow_button.setArrowType(
            QtCore.Qt.ArrowType.RightArrow if collapsed else QtCore.Qt.ArrowType.DownArrow
        )

    def set_icon(self, icon: t.Optional[QtGui.QIcon]) -> None:
        if icon is not None:
            self.icon_label.setVisible(True)
            self.icon_label.setPixmap(icon.pixmap(self._ICON_SIZE))
        else:
            self.icon_label.setVisible(False)

    def _on_toggle(self, checked: bool) -> None:
        self.set_collapsed(not checked)
