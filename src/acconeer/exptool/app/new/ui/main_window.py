# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import typing as t
from enum import IntEnum, auto

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app.new.app_model import AppModel

from .flash_tab import FlashWizard
from .help_tab import HelpMainWidget
from .icons import FLASH, GAUGE, HELP, RECORD
from .misc import ExceptionWidget
from .resource_tab import ResourceMainWidget
from .status_bar import StatusBar
from .stream_tab import StreamingMainWidget
from .utils import LayoutWrapper, TopAlignDecorator


class _IconButton(QToolButton):
    def __init__(
        self,
        icon: QIcon,
        text: str,
        is_active: bool,
        is_checkable: bool,
        icon_size: int = 30,
        tooltip: str = "",
    ) -> None:
        super().__init__()

        self.setCheckable(is_checkable)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,  # horizontal
            QSizePolicy.Policy.Fixed,  # vertical
        )

        self.setIcon(icon)
        self.setText(text)
        self.setChecked(is_active)
        if tooltip:
            self.setToolTip(tooltip)


class _PagedLayout(QSplitter):
    """
    The widget that is responsible for the paged main widget:

        Buttons          Page
           |              |
           V              V
        +--------+------------------+
        | Stream |                  |
        +--------+                  |
        | Flash  |                  |
        +--------+                  |
        | RC     |                  |
        +--------+                  |
        | Help   |                  |
        +--------+                  |
        |   .    |                  |
        |   .    |                  |
        |        |                  |
        +--------+------------------+
    """

    class _ButtonId(IntEnum):
        STREAM = auto()
        FLASH = auto()
        RESOURCE_CALCULATOR = auto()
        HELP = auto()

    def __init__(
        self,
        app_model: AppModel,
        *,
        index_button_width: int = 60,
    ) -> None:
        super().__init__()

        self.app_model = app_model
        self.app_model.sig_notify.connect(self._on_app_model_update)

        self._index_button_group = QButtonGroup()
        self._index_button_layout = QVBoxLayout()
        self._index_button_layout.setContentsMargins(0, 0, 0, 0)

        self._page_widget = QStackedWidget()

        # Index buttons/Tabs
        stream_index_button = _IconButton(
            RECORD(),
            "Stream",
            is_checkable=True,
            is_active=True,
            tooltip="",
        )
        self._stream_main_widget = StreamingMainWidget(self.app_model, self)
        self._index_button_group.addButton(stream_index_button, id=self._ButtonId.STREAM)
        self._index_button_layout.addWidget(stream_index_button)
        self._page_widget.addWidget(self._stream_main_widget)

        flash_index_button = _IconButton(
            FLASH(),
            "Flash",
            is_checkable=False,
            is_active=False,
            tooltip="",
        )
        self._index_button_group.addButton(flash_index_button, id=self._ButtonId.FLASH)
        self._index_button_layout.addWidget(flash_index_button)

        rc_tooltip = "Resource Calculator"
        rc_index_button = _IconButton(
            GAUGE(),
            "RC",
            is_checkable=True,
            is_active=False,
            tooltip=rc_tooltip,
        )
        self._resource_main_widget = ResourceMainWidget()
        self._index_button_group.addButton(rc_index_button, id=self._ButtonId.RESOURCE_CALCULATOR)
        self._index_button_layout.addWidget(rc_index_button)
        self._page_widget.addWidget(self._resource_main_widget)
        # Signals for "Goto resource calculator".
        self.app_model.sig_resource_tab_input_block_requested.connect(
            self._resource_main_widget.spawn_input_block
        )
        self.app_model.sig_resource_tab_input_block_requested.connect(
            lambda: self.setCurrentWidget(self._resource_main_widget)
        )

        help_index_button = _IconButton(
            HELP(),
            "Help",
            is_checkable=True,
            is_active=False,
            tooltip="",
        )
        self._help_main_widget = HelpMainWidget(self)
        self._index_button_group.addButton(help_index_button, id=self._ButtonId.HELP)
        self._index_button_layout.addWidget(help_index_button)
        self._page_widget.addWidget(self._help_main_widget)

        self._index_button_group.idClicked.connect(self.index_button_clicked)
        self._index_button_widget = TopAlignDecorator(LayoutWrapper(self._index_button_layout))
        self._index_button_widget.setFixedWidth(index_button_width)
        self.addWidget(self._index_button_widget)
        self.addWidget(self._page_widget)
        self.setCollapsible(1, False)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self._index_button_widget.setEnabled(app_model.plugin_state.is_steady)

    def index_button_clicked(self, index_button_id: int) -> None:
        if index_button_id == self._ButtonId.STREAM:
            self.setCurrentWidget(self._stream_main_widget)
        elif index_button_id == self._ButtonId.FLASH:
            FlashWizard(self.app_model).exec()
        elif index_button_id == self._ButtonId.RESOURCE_CALCULATOR:
            self.setCurrentWidget(self._resource_main_widget)
        elif index_button_id == self._ButtonId.HELP:
            self.setCurrentWidget(self._help_main_widget)
        else:
            msg = f"Unknown index_button_id: {index_button_id}"
            raise ValueError(msg)

    def setCurrentWidget(self, widget: QWidget) -> None:
        if widget is self._stream_main_widget:
            self._page_widget.setCurrentWidget(self._stream_main_widget)
            self._index_button_group.button(self._ButtonId.STREAM).setChecked(True)
        elif widget is self._resource_main_widget:
            self._page_widget.setCurrentWidget(self._resource_main_widget)
            self._index_button_group.button(self._ButtonId.RESOURCE_CALCULATOR).setChecked(True)
        elif widget is self._help_main_widget:
            self._page_widget.setCurrentWidget(self._help_main_widget)
            self._index_button_group.button(self._ButtonId.HELP).setChecked(True)
        else:
            msg = f"Unknown widget: {widget}"
            raise ValueError(msg)


class MainWindow(QMainWindow):
    sig_closing = Signal()

    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        paged_layout = _PagedLayout(app_model)

        self.setCentralWidget(paged_layout)

        self.setStatusBar(StatusBar(app_model, self))
        self.setWindowTitle("Acconeer Exploration Tool")
        self.moveEvent = lambda _: self.saveGeometry()  # type: ignore[method-assign,assignment]

        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_error(self, exception: Exception, traceback_str: t.Optional[str]) -> None:
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()

    def closeEvent(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.sig_closing.emit()
        return super().closeEvent(*args, **kwargs)
