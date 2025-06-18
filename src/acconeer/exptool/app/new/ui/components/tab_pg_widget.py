# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import contextlib
from copy import copy
from typing import List, Optional

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool.app.new.ui.utils import LayoutWrapper, LeftAlignDecorator


class TabPGWidget(QFrame):
    """
    Custom tab widget to handle GraphicsLayoutWidget.
    Since QTabWidget and GraphicsLayoutWidget caused GUI to freeze.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent=parent)

        self._button_group = QButtonGroup()
        self._button_layout = QHBoxLayout()
        self._button_layout.setContentsMargins(0, 0, 0, 0)

        self._main_layout = QVBoxLayout()
        button_wrapper = LeftAlignDecorator(LayoutWrapper(self._button_layout))
        self._main_layout.addWidget(button_wrapper)

        self._plot_widgets: List[pg.GrachicsLayoutWidget] = []

        self.setLayout(self._main_layout)

    def newPlotWidget(self, title: str) -> pg.GraphicsLayoutWidget:
        plot_widget = pg.GraphicsLayoutWidget()
        self.newTab(plot_widget, title)
        return plot_widget

    def newTab(self, widget: QWidget, title: str) -> None:
        new_tab_id = len(self._button_group.buttons())
        widget.setVisible(new_tab_id == 0)
        self._plot_widgets.append(widget)
        self._main_layout.addWidget(widget)

        button = QPushButton(title, self)
        button.setCheckable(True)
        button.setChecked(new_tab_id == 0)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._button_group.addButton(button, id=len(self._button_group.buttons()))
        self._button_group.idToggled.connect(
            lambda button_id, checked: widget.setVisible(button_id == new_tab_id and checked)
        )
        self._button_layout.addWidget(button)

    def clear(self) -> None:
        if len(self._button_group.buttons()) > 0:
            with contextlib.suppress(RuntimeError, RuntimeWarning):
                self._button_group.idToggled.disconnect()

        for plot_widget in self._plot_widgets:
            self._main_layout.removeWidget(plot_widget)
            plot_widget.deleteLater()

        self._plot_widgets = []

        for button in copy(self._button_group.buttons()):
            self._button_group.removeButton(button)
            self._button_layout.removeWidget(button)
            button.deleteLater()
