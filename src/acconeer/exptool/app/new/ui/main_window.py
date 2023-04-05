# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

import typing as t

from PySide6.QtCore import QSize, Qt
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
from .icons import FLASH, HELP, RECORD
from .misc import ExceptionWidget
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
        self, pages: t.Iterable[t.Tuple[QIcon, str, QWidget]], *, index_button_width: int = 60
    ) -> None:
        super().__init__()
        self._index_button_group = QButtonGroup()
        self._index_button_layout = QVBoxLayout()
        self._index_button_layout.setContentsMargins(0, 0, 0, 0)

        self._page_widget = QStackedWidget()

        for i, (icon, text, page) in enumerate(pages):
            index_button = _IconButton(icon, text, is_active=i == 0)

            self._index_button_group.addButton(index_button, id=i)
            self._index_button_layout.addWidget(index_button)
            self._page_widget.addWidget(page)

        self._index_button_group.idClicked.connect(self._page_widget.setCurrentIndex)
        index_button_widget = TopAlignDecorator(LayoutWrapper(self._index_button_layout))
        index_button_widget.setFixedWidth(index_button_width)
        self.addWidget(index_button_widget)
        self.addWidget(self._page_widget)
        self.setCollapsible(1, False)


class MainWindow(QMainWindow):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()

        self.resize(1280, 720)

        self.setCentralWidget(
            _PagedLayout(
                [
                    (RECORD(), "Stream", StreamingMainWidget(app_model, self)),
                    (FLASH(), "Flash", FlashMainWidget(app_model, self)),
                    (HELP(), "Help", HelpMainWidget(self)),
                ]
            )
        )

        self.setStatusBar(StatusBar(app_model, self))
        self.setWindowTitle("Acconeer Exploration Tool")
        self.moveEvent = lambda _: self.saveGeometry()

        app_model.sig_error.connect(self.on_app_model_error)

    def on_app_model_error(self, exception: Exception, traceback_str: t.Optional[str]) -> None:
        ExceptionWidget(self, exc=exception, traceback_str=traceback_str).exec()
