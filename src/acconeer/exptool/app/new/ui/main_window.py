# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import typing as t

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

from .flash_tab import FlashMainWidget
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
        icon_size: int = 30,
        tooltip: str = "",
    ) -> None:
        super().__init__()

        self.setCheckable(True)
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

       Index      Page
         |         |
         V         V
        +-+------------------+
        |A|                  |
        +-+                  |
        |B|      Page A      |
        +-+                  |
        | |                  |
        +-+------------------+
    """

    def __init__(
        self,
        app_model: AppModel,
        pages: t.Iterable[t.Tuple[QIcon, str, QWidget, str]],
        *,
        index_button_width: int = 60,
    ) -> None:
        super().__init__()
        app_model.sig_notify.connect(self._on_app_model_update)

        self._index_button_group = QButtonGroup()
        self._index_button_layout = QVBoxLayout()
        self._index_button_layout.setContentsMargins(0, 0, 0, 0)

        self._page_widget = QStackedWidget()

        for i, (icon, text, page, tooltip) in enumerate(pages):
            index_button = _IconButton(icon, text, is_active=i == 0, tooltip=tooltip)

            self._index_button_group.addButton(index_button, id=i)
            self._index_button_layout.addWidget(index_button)
            self._page_widget.addWidget(page)

        self._index_button_group.idClicked.connect(self._page_widget.setCurrentIndex)
        self._index_button_widget = TopAlignDecorator(LayoutWrapper(self._index_button_layout))
        self._index_button_widget.setFixedWidth(index_button_width)
        self.addWidget(self._index_button_widget)
        self.addWidget(self._page_widget)
        self.setCollapsible(1, False)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self._index_button_widget.setEnabled(app_model.plugin_state.is_steady)

    def setCurrentWidget(self, widget: QWidget) -> None:
        idx = self._page_widget.indexOf(widget)
        if idx == -1:
            msg = f"Passed widget is not part of {type(self).__name__}"
            raise ValueError(msg)

        self._index_button_group.button(idx).click()


class MainWindow(QMainWindow):
    sig_closing = Signal()

    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        resource_widget = ResourceMainWidget()
        paged_layout = _PagedLayout(
            app_model,
            [
                (RECORD(), "Stream", StreamingMainWidget(app_model, self), ""),
                (FLASH(), "Flash", FlashMainWidget(app_model, self), ""),
                (GAUGE(), "RC", resource_widget, "Resource Calculator"),
                (HELP(), "Help", HelpMainWidget(self), ""),
            ],
        )

        app_model.sig_resource_tab_input_block_requested.connect(resource_widget.spawn_input_block)
        app_model.sig_resource_tab_input_block_requested.connect(
            lambda: paged_layout.setCurrentWidget(resource_widget)
        )

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
