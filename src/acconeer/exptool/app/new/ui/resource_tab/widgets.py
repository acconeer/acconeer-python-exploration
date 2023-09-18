# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import json
import logging
import typing as t
from pathlib import Path

import attrs
import typing_extensions as te

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QToolBar,
    QToolButton,
    QWidget,
)

import acconeer.exptool
from acconeer.exptool.app.new.storage import get_config_dir
from acconeer.exptool.app.new.ui.icons import CHART_BAR, CHART_LINE, CLOSE, COG, INFO, MEMORY
from acconeer.exptool.utils import get_module_version

from .event_system import EventBroker
from .services import (
    memory_breakdown_output,
    power_consumption_vs_rate_output,
    power_curve_output,
    session_config_input,
)


_QWidgetT = t.TypeVar("_QWidgetT", bound=t.Type[QWidget])


log = logging.getLogger(__name__)

_ALLOWED_DOCK_AREA = Qt.DockWidgetArea.BottomDockWidgetArea

_DATA_IS_APPROXIMATE_DESCRIPTION = "\n\n".join(
    [
        "All data and numbers presented in this tab are approximations. "
        + "The goal is to let you experiment with configurations and do comparisons.",
        "Use this tool as a way to quickly narrow down which configuration could satisfy your "
        + "constraints before you do measurements to get real numbers.",
    ]
)


_TAB_BRIEF_DESCRIPTION = "\n\n".join(
    [
        "This tab allows you to experiment and visualize resource "
        + "requirements for different configurations. ",
        'The top bar is a palette with all the "blocks" you can use. '
        + "Click on them to add an additional block of that type.",
        "Some blocks have an id in [brackets] in the title bar. "
        + "This is used to connect inputs and outputs.",
        "You can hover a block's info icon for a longer description "
        + "of what the block does and how you may use it.",
    ]
)


@attrs.mutable
class _UserUnderstandings:
    """
    Simple class that keeps track of what the user understands.

    Used to control pop-ups with information when opening the resource tab.
    """

    _PATH: t.ClassVar[Path] = get_config_dir() / "user_understandings.json"

    data_is_approximate: bool
    tab_brief: bool
    lib_version: str

    @classmethod
    def require(cls) -> te.Self:
        """Returns a persisted instance or creates a new instance"""
        try:
            with cls._PATH.open("r") as file:
                return cls(**json.load(file))
        except (FileNotFoundError, json.JSONDecodeError):
            return cls(
                data_is_approximate=False,
                tab_brief=False,
                lib_version=get_module_version(acconeer.exptool),
            )

    def save(self) -> None:
        with self._PATH.open("w") as file:
            return json.dump(attrs.asdict(self), file)


class _TitleBarLabel(QLabel):
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        event.ignore()


class _TitleBarWidget(QWidget):
    sig_exit_clicked = Signal()

    def __init__(
        self,
        title: str,
        tooltip: str,
        parent: QWidget,
    ) -> None:
        super().__init__(parent=parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName("_TitleBarWidget")
        self.setStyleSheet("#_TitleBarWidget { background: #ebebeb; }")

        title_label = _TitleBarLabel(title)
        title_label.setTextFormat(Qt.TextFormat.RichText)

        info_icon = QToolButton()
        info_icon.setIcon(INFO())
        info_icon.setIconSize(QSize(16, 16))
        info_icon.setDisabled(True)
        info_icon.setToolTip(tooltip)

        close_button = QToolButton()
        close_button.setIcon(CLOSE())
        close_button.clicked.connect(self.sig_exit_clicked.emit)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title_label, stretch=0)
        layout.addWidget(info_icon, stretch=0, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(close_button, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)

        self.setLayout(layout)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        event.ignore()


class _DockWidget(QDockWidget):
    def __init__(
        self,
        title: str,
        tooltip: str,
        widget: QWidget,
        close_hook: t.Callable[[], None],
        parent: QWidget,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle(title)

        self.setWidget(widget)
        self.setAllowedAreas(_ALLOWED_DOCK_AREA)
        self._close_hook = close_hook

        title_bar = _TitleBarWidget(title, tooltip, self)
        title_bar.sig_exit_clicked.connect(close_hook)
        title_bar.sig_exit_clicked.connect(self.close)
        self.setTitleBarWidget(title_bar)


class ResourceMainWidget(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self._broker = EventBroker()

        # default is AnimatedDocks | AllowTabbedDocks
        self.setDockOptions(
            QMainWindow.DockOption.AllowNestedDocks | QMainWindow.DockOption.AnimatedDocks
        )

        toolbar = QToolBar()
        toolbar.setFixedHeight(64)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setFloatable(False)
        toolbar.setMovable(False)

        self._add_spawn_buttons(toolbar)
        self.setCentralWidget(toolbar)

        # Default loadout
        power_curve = self._create_power_curve_output()
        self._add_dock_widget(power_curve)
        self._add_dock_widget_below_target(
            target=power_curve,
            new_widget=self._create_memory_breakdown_output(),
        )
        self._add_dock_widget_right_of_target(
            target=power_curve,
            new_widget=self._create_power_consumption_vs_rate_output(),
        )
        self._add_dock_widget(self._create_session_config_input())

    def showEvent(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().showEvent(*args, **kwargs)

        user_understandings = _UserUnderstandings.require()

        if not user_understandings.data_is_approximate:
            pressed_button = QMessageBox.information(
                self, "Data is approximate", _DATA_IS_APPROXIMATE_DESCRIPTION
            )
            user_understandings.data_is_approximate = (
                pressed_button == QMessageBox.StandardButton.Ok
            )

        if not user_understandings.tab_brief:
            pressed_button = QMessageBox.information(
                self, "Resource Calculator", _TAB_BRIEF_DESCRIPTION
            )
            user_understandings.tab_brief = pressed_button == QMessageBox.StandardButton.Ok

        user_understandings.save()

    def _add_dock_widget(self, dockwidget: QDockWidget) -> None:
        super().addDockWidget(_ALLOWED_DOCK_AREA, dockwidget)

    def _add_dock_widget_below_target(self, target: QDockWidget, new_widget: QDockWidget) -> None:
        super().splitDockWidget(target, new_widget, Qt.Orientation.Vertical)

    def _add_dock_widget_right_of_target(
        self, target: QDockWidget, new_widget: QDockWidget
    ) -> None:
        super().splitDockWidget(target, new_widget, Qt.Orientation.Horizontal)

    def _create_action(
        self,
        icon: QIcon,
        button_label: str,
        on_trigger: t.Callable[[], t.Any],
    ) -> QAction:
        action = QAction(icon, button_label, parent=self)
        action.triggered.connect(on_trigger)
        return action

    def _add_spawn_buttons(self, toolbar: QToolBar) -> None:
        actions = [
            self._create_action(
                COG(),
                button_label="Sparse IQ config",
                on_trigger=lambda: self._add_dock_widget(self._create_session_config_input()),
            ),
            self._create_action(
                CHART_BAR(),
                button_label="Power curve",
                on_trigger=lambda: self._add_dock_widget(self._create_power_curve_output()),
            ),
            self._create_action(
                CHART_LINE(),
                button_label="Power consumption vs. Rate",
                on_trigger=lambda: self._add_dock_widget(
                    self._create_power_consumption_vs_rate_output()
                ),
            ),
            self._create_action(
                MEMORY(),
                button_label="Memory breakdown",
                on_trigger=lambda: self._add_dock_widget(self._create_memory_breakdown_output()),
            ),
        ]

        for action in actions:
            toolbar.addAction(action)

    def _create_session_config_input(self) -> _DockWidget:
        service = session_config_input.SessionConfigInput(self._broker)
        return _DockWidget(
            service.window_title,
            service.description,
            service,
            service.uninstall_function,
            parent=self,
        )

    def _create_power_curve_output(self) -> _DockWidget:
        service = power_curve_output.EnergyRegionOutput(self._broker)
        return _DockWidget(
            service.window_title,
            service.description,
            service,
            service.uninstall_function,
            parent=self,
        )

    def _create_power_consumption_vs_rate_output(self) -> _DockWidget:
        service = power_consumption_vs_rate_output.PowerConsumptionVsRateOutput(self._broker)
        return _DockWidget(
            service.window_title,
            service.description,
            service,
            service.uninstall_function,
            parent=self,
        )

    def _create_memory_breakdown_output(self) -> _DockWidget:
        service = memory_breakdown_output.MemoryBreakdownOutput(self._broker)
        return _DockWidget(
            service.window_title,
            service.description,
            service,
            service.uninstall_function,
            parent=self,
        )
