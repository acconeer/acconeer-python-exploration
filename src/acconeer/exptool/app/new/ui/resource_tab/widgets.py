# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import json
import logging
import typing as t
from pathlib import Path

import attrs
import typing_extensions as te
from packaging.version import Version

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QDockWidget,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolBar,
    QToolButton,
    QWidget,
)

import acconeer.exptool
from acconeer.exptool import a121
from acconeer.exptool.a121.algo import distance, presence
from acconeer.exptool.app.new.storage import get_config_dir
from acconeer.exptool.app.new.ui.icons import CHART_BAR, CHART_LINE, CLOSE, COG, EDIT, INFO, MEMORY
from acconeer.exptool.utils import get_module_version

from .animation import run_blink_animation
from .event_system import ChangeIdEvent, EventBroker
from .services import (
    distance_config_input,
    memory_breakdown_output,
    power_consumption_vs_rate_output,
    power_curve_output,
    presence_config_input,
    session_config_input,
)


_QWidgetT = t.TypeVar("_QWidgetT", bound=t.Type[QWidget])


log = logging.getLogger(__name__)

_ALLOWED_DOCK_AREA = Qt.DockWidgetArea.BottomDockWidgetArea

_DATA_IS_APPROXIMATE_DESCRIPTION = "<br><br>".join(
    [
        "All data and numbers presented in this tab are approximations based on RSS A121-v1.12.0, <b>not measurements</b>.",
        "The goal is to let you experiment with configurations and do comparisons.",
        "Use this tool as a way to quickly narrow down which configuration could satisfy your "
        + "constraints before you do measurements to get real numbers.",
    ]
)


_TAB_BRIEF_DESCRIPTION = "<br><br>".join(
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
    tab_brief: bool  # Not used anymore
    lib_version: str

    @classmethod
    def require(cls) -> te.Self:
        """Returns a persisted instance or creates a new instance"""
        try:
            with cls._PATH.open("r") as file:
                cached = cls(**json.load(file))

                if Version(cached.lib_version) < Version("v7.6.1"):
                    # v7.6.1 slightly modified the approximate disclaimer text to
                    # emphasize that the numbers displayed are not measurements.
                    cached.data_is_approximate = False

                return cached
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
    def __init__(self, text: str, parent: t.Optional[QWidget] = None) -> None:
        super().__init__(text=text, parent=parent)
        self.setTextFormat(Qt.TextFormat.RichText)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.ignore()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        event.ignore()


class _EditableTitleBarLabel(QWidget):
    INTERESTS: t.ClassVar[set[type]] = {ChangeIdEvent}
    description: t.ClassVar[str] = ""
    window_title: str = ""

    def __init__(self, text: str, broker: EventBroker, parent: t.Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self._broker = broker

        layout = QHBoxLayout(self)

        self.label = _TitleBarLabel(text, self)
        layout.addWidget(self.label)

        edit_button = QPushButton()
        edit_button.setIcon(EDIT())
        edit_button.clicked.connect(self._on_edit_title)
        layout.addWidget(edit_button)

        self.setLayout(layout)

        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)

    def _on_edit_title(self) -> None:
        text, ok = QInputDialog.getText(self, "Edit title", "Title:", text=self.text())

        if ok and text and text != self.text():
            text = self._broker.change_id(text, self.text())
            self._broker.offer_event(ChangeIdEvent(self.text(), text))

    def text(self) -> str:
        return self.label.text()[3:-3]

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, ChangeIdEvent):
            self._handle_change_id_event(event)
        else:
            raise NotImplementedError

    def _handle_change_id_event(self, event: ChangeIdEvent) -> None:
        if self.text() == event.old_id:
            self.label.setText(f"<b>{event.new_id}<\b>")

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

        fixed_label = _TitleBarLabel(title)

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
        layout.addWidget(fixed_label, stretch=0)
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


class _EditableTitleBarWidget(_TitleBarWidget):
    def __init__(
        self,
        editable_title: t.Optional[str],
        fixed_title: str,
        tooltip: str,
        broker: EventBroker,
        parent: QWidget,
    ) -> None:
        super().__init__(fixed_title, tooltip, parent)

        if editable_title is not None:
            self.editable_label = _EditableTitleBarLabel(f"<b>{editable_title}<\b>", broker)
            layout = self.layout()
            if isinstance(layout, QBoxLayout):
                layout.insertWidget(1, self.editable_label, stretch=0)


@attrs.frozen
class _SpawnInputEvent:
    compare_configs: bool


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
        self.title = title
        self.tooltip = tooltip
        self.setWindowTitle(title)

        self.setWidget(widget)
        self.setAllowedAreas(_ALLOWED_DOCK_AREA)
        self._close_hook = close_hook

        self._set_title_bar_widget()

    def _set_title_bar_widget(self) -> None:
        title_bar = _TitleBarWidget(self.title, self.tooltip, self)
        title_bar.sig_exit_clicked.connect(self.close)
        self.setTitleBarWidget(title_bar)

    def close(self) -> bool:
        self._close_hook()
        return super().close()


class _InputDockWidget(_DockWidget):
    INTERESTS: t.ClassVar[set[type]] = {_SpawnInputEvent, ChangeIdEvent}
    description: t.ClassVar[str] = ""

    def __init__(
        self,
        id_: str,
        fixed_title: str,
        tooltip: str,
        widget: QWidget,
        close_hook: t.Callable[[], None],
        broker: EventBroker,
        parent: QWidget,
    ) -> None:
        self._id = id_
        self._fixed_title = fixed_title
        self._broker = broker
        super().__init__(fixed_title, tooltip, widget, close_hook, parent=parent)
        self.window_title = f"{self._fixed_title} - {self._id}"
        broker.install_service(self)
        self.uninstall_function = lambda: broker.uninstall_service(self)

    def _set_title_bar_widget(self) -> None:
        title_bar = _EditableTitleBarWidget(
            self._id, self._fixed_title, self.tooltip, self._broker, self
        )
        title_bar.sig_exit_clicked.connect(self.close)
        self.setTitleBarWidget(title_bar)

    def handle_event(self, event: t.Any) -> None:
        if isinstance(event, _SpawnInputEvent) and not event.compare_configs:
            self.close()
        if isinstance(event, ChangeIdEvent) and self._id == event.old_id:
            self._id = event.new_id
            self.window_title = f"{self._fixed_title} - {self._id}"

    def close(self) -> bool:
        self.uninstall_function()
        return super().close()


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

        self._compare_cb = QCheckBox("Compare")
        self._compare_cb.setToolTip(
            "Allow to open multiple configurations within the window to compare plots and numbers."
        )
        self._compare_cb.setChecked(False)

        self._populate_palette(toolbar)
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
        self.spawn_input_block(a121.SessionConfig(), animate=False)

    def showEvent(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().showEvent(*args, **kwargs)

        user_understandings = _UserUnderstandings.require()

        if not user_understandings.data_is_approximate:
            disclaimer_box = QMessageBox(
                QMessageBox.Icon.Information,
                "Data is approximate",
                _DATA_IS_APPROXIMATE_DESCRIPTION,
                parent=self,
            )
            understand_cb = QCheckBox("I understand", self)
            disclaimer_box.setCheckBox(understand_cb)
            disclaimer_box.exec()
            user_understandings.data_is_approximate = understand_cb.isChecked()

        user_understandings.save()

    def spawn_input_block(self, config: t.Any, animate: bool = True) -> None:
        self._broker.offer_event(_SpawnInputEvent(self._compare_cb.isChecked()))

        if isinstance(config, a121.SessionConfig):
            dock_widget = self._create_session_config_input(config)
        elif isinstance(config, distance.DetectorConfig):
            dock_widget = self._create_distance_config_input(config)
        elif isinstance(config, presence.DetectorConfig):
            dock_widget = self._create_presence_config_input(config)
        else:
            return

        self._add_dock_widget(dock_widget)
        if animate:
            run_blink_animation(dock_widget)

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

    def _populate_palette(self, toolbar: QToolBar) -> None:
        toolbar.addAction(
            self._create_action(
                COG(),
                button_label="New Sparse IQ config",
                on_trigger=lambda: self.spawn_input_block(a121.SessionConfig(), animate=False),
            )
        )
        toolbar.addAction(
            self._create_action(
                COG(),
                "New Distance config",
                on_trigger=lambda: self.spawn_input_block(
                    distance.DetectorConfig(), animate=False
                ),
            )
        )
        toolbar.addAction(
            self._create_action(
                COG(),
                "New Presence config",
                on_trigger=lambda: self.spawn_input_block(
                    presence.DetectorConfig(), animate=False
                ),
            )
        )

        toolbar.addSeparator()

        toolbar.addAction(
            self._create_action(
                CHART_BAR(),
                button_label="Power curve",
                on_trigger=lambda: self._add_dock_widget(self._create_power_curve_output()),
            )
        )

        toolbar.addAction(
            self._create_action(
                CHART_LINE(),
                button_label="Power consumption vs. Rate",
                on_trigger=lambda: self._add_dock_widget(
                    self._create_power_consumption_vs_rate_output()
                ),
            )
        )
        toolbar.addAction(
            self._create_action(
                MEMORY(),
                button_label="Memory breakdown",
                on_trigger=lambda: self._add_dock_widget(self._create_memory_breakdown_output()),
            )
        )

        toolbar.addSeparator()

        toolbar.addAction(
            self._create_action(
                INFO(),
                button_label="Info",
                on_trigger=lambda: self._show_info_popup(),
            )
        )

        toolbar.addSeparator()

        toolbar.addWidget(self._compare_cb)

    def _create_session_config_input(self, config: a121.SessionConfig) -> _DockWidget:
        service = session_config_input.SessionConfigInput(self._broker, config)
        return _InputDockWidget(
            service.id_,
            service.fixed_title,
            service.description,
            service,
            service.uninstall_function,
            self._broker,
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

    def _create_distance_config_input(self, config: distance.DetectorConfig) -> _DockWidget:
        service = distance_config_input.DistanceConfigInput(self._broker, config)
        return _InputDockWidget(
            service.id_,
            service.fixed_title,
            service.description,
            service,
            service.uninstall_function,
            self._broker,
            parent=self,
        )

    def _create_presence_config_input(self, config: presence.DetectorConfig) -> _DockWidget:
        service = presence_config_input.PresenceConfigInput(self._broker, config)
        return _InputDockWidget(
            service.id_,
            service.fixed_title,
            service.description,
            service,
            service.uninstall_function,
            self._broker,
            parent=self,
        )

    def _show_info_popup(self) -> None:
        txt = "<h2>How to use</h2>"
        txt += _TAB_BRIEF_DESCRIPTION
        txt += "<h2>Disclaimer</h2>"
        txt += _DATA_IS_APPROXIMATE_DESCRIPTION
        QMessageBox.information(self, "Resource Calculator", txt)
