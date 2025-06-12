# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import logging
from enum import Enum
from functools import partial
from importlib.resources import as_file, files
from typing import Any, Optional

import qtawesome as qta

from PySide6 import QtCore, QtGui
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool.app import resources
from acconeer.exptool.app.new._enums import PluginFamily, PluginGeneration, PluginState
from acconeer.exptool.app.new.app_model import AppModel, PluginPresetSpec, PluginSpec
from acconeer.exptool.app.new.pluginbase import PlotPluginBase, PluginSpecBase
from acconeer.exptool.app.new.ui.components.group_box import GroupBox
from acconeer.exptool.app.new.ui.icons import ARROW_LEFT_BOLD, EXTERNAL_LINK, TEXT_GREY
from acconeer.exptool.app.new.ui.utils import (
    HorizontalSeparator,
    LayoutWrapper,
    ScrollAreaDecorator,
    TopAlignDecorator,
)


log = logging.getLogger(__name__)


class PluginSelectionButton(QPushButton):
    plugin: PluginSpec

    def __init__(self, plugin: PluginSpecBase, parent: QWidget) -> None:
        super().__init__(parent)

        self.plugin = plugin

        self.setText(plugin.title)
        self.setStyleSheet("text-align: left; font-weight: bold;")
        self.setCheckable(True)


class PluginSelectionButtonGroup(QButtonGroup):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setExclusive(True)

    def checkedButton(self) -> PluginSelectionButton:
        button = super().checkedButton()
        assert isinstance(button, PluginSelectionButton)
        return button

    def buttons(self) -> list[PluginSelectionButton]:  # type: ignore[override]
        buttons = super().buttons()
        assert isinstance(buttons, list)
        assert all(isinstance(e, PluginSelectionButton) for e in buttons)
        return buttons  # type: ignore[return-value]


class PluginPresetButton(QPushButton):
    def __init__(self, plugin_preset: PluginPresetSpec, default: bool, parent: QWidget) -> None:
        super().__init__(parent)

        if default:
            self.setText(f"{plugin_preset.name} (default)")
        else:
            self.setText(plugin_preset.name)
        if plugin_preset.description is not None:
            self.setToolTip(plugin_preset.description)
        self.setStyleSheet("text-align: left; font-weight: bold;")


class PluginPresetPlaceholder(QWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.app_model = app_model
        self.app_model.sig_load_plugin.connect(self._on_load_plugin)
        self.app_model.sig_notify.connect(self._on_app_model_update)

        self.app_model = app_model
        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)
        self.group_box = GroupBox.vertical("Preset Configurations", parent=self)
        layout.addWidget(self.group_box)
        self.preset_buttons_widget: Optional[QWidget] = None

        self.setLayout(layout)

    def _clear(self) -> None:
        if self.preset_buttons_widget is not None:
            self.preset_buttons_widget.deleteLater()
            self.preset_buttons_widget = None

    def _on_preset_click(self, preset_id: Enum) -> None:
        self.app_model.set_plugin_preset(preset_id)

    def _on_load_plugin(self, plugin_spec: Optional[PluginSpecBase]) -> None:
        self._clear()
        if plugin_spec is not None and plugin_spec.presets is not None:
            self.preset_buttons_widget = QWidget(self.group_box)
            preset_buttons_layout = QVBoxLayout(self.preset_buttons_widget)
            preset_buttons_layout.setContentsMargins(0, 0, 0, 0)

            self.group_box.layout().addWidget(self.preset_buttons_widget)

            for preset in plugin_spec.presets:
                default_preset = (
                    len(plugin_spec.presets) > 1
                    and preset.preset_id == plugin_spec.default_preset_id
                    and preset.name.lower() != "default"
                )
                button = PluginPresetButton(preset, default_preset, self)
                preset_buttons_layout.addWidget(button)
                button.clicked.connect(partial(self._on_preset_click, preset.preset_id))
            self.preset_buttons_widget.setLayout(preset_buttons_layout)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        self.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)


class PluginSelection(QWidget):
    PLUGIN_FAMILY_ORDER = [
        PluginFamily.EXTERNAL_PLUGIN,
        PluginFamily.SERVICE,
        PluginFamily.DETECTOR,
        PluginFamily.REF_APP,
        PluginFamily.EXAMPLE_APP,
    ]

    def __init__(
        self, app_model: AppModel, plugins: list[PluginSpecBase], parent: QWidget
    ) -> None:
        super().__init__(parent)

        self.app_model = app_model

        app_model.sig_notify.connect(self._on_app_model_update)
        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)

        group_boxes = {}
        for family in self.PLUGIN_FAMILY_ORDER:
            group_box = QGroupBox(self)
            group_box.setTitle(family.value)
            group_box.setHidden(True)
            group_box.setLayout(QVBoxLayout(group_box))
            layout.addWidget(group_box)
            group_boxes[family] = group_box

        self.button_group = PluginSelectionButtonGroup(self)
        self.button_group.buttonClicked.connect(self._on_load_click)

        for plugin in plugins:
            assert isinstance(plugin, PluginSpecBase)
            group_box = group_boxes[plugin.family]
            group_box.setHidden(False)

            button_layout = QHBoxLayout()
            button_layout.setContentsMargins(0, 0, 0, 0)

            group_box_layout = group_box.layout()
            assert group_box_layout is not None
            group_box_layout.addWidget(LayoutWrapper(button_layout))

            button = PluginSelectionButton(plugin, group_box)
            self.button_group.addButton(button)
            button_layout.addWidget(button)

            if plugin.description:
                label = QLabel(group_box)
                label.setText(plugin.description)
                label.setWordWrap(True)
                group_box_layout.addWidget(label)

            if plugin.docs_link:
                info_button = QPushButton(QtGui.QIcon(EXTERNAL_LINK(color=TEXT_GREY)), "docs")
                info_button.setStyleSheet(f"QPushButton {{color: {TEXT_GREY}}}")
                info_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                info_button.clicked.connect(
                    lambda _=False, p=plugin: QtGui.QDesktopServices.openUrl(p.docs_link)
                )
                button_layout.addWidget(info_button)
        self.setLayout(layout)

    def layout(self) -> QVBoxLayout:
        return super().layout()  # type: ignore[return-value]

    def _on_load_click(self) -> None:
        self.layout().addStretch(1)

        plugin = self.button_group.checkedButton().plugin
        self.app_model.load_plugin(plugin)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        plugin: Optional[PluginSpec] = app_model.plugin

        if plugin is None:
            self.button_group.setExclusive(False)

            for button in self.button_group.buttons():
                button.setChecked(False)

            self.button_group.setExclusive(True)
        else:
            buttons = self.button_group.buttons()
            try:
                (button_to_check,) = {b for b in buttons if b.plugin == plugin}
            except ValueError:
                pass
            else:
                button_to_check.setChecked(True)

        self.setEnabled(app_model.plugin_state.is_steady)


class PluginSelectionArea(QWidget):
    def __init__(self, app_model: AppModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        a121_selection = ScrollAreaDecorator(
            TopAlignDecorator(
                PluginSelection(
                    app_model,
                    [
                        plugin
                        for plugin in app_model.plugins
                        if (
                            plugin.generation == PluginGeneration.A121
                            and isinstance(plugin, PluginSpecBase)
                        )
                    ],
                    self,
                )
            )
        )
        a121_selection.setVisible(True)

        app_model.sig_notify.connect(
            lambda am: a121_selection.setVisible(am.plugin_generation == PluginGeneration.A121)
        )

        layout.addWidget(a121_selection)
        layout.addWidget(HorizontalSeparator())
        layout.addWidget(PluginPresetPlaceholder(app_model, self))
        self.setLayout(layout)


class PlotPlaceholder(PlotPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        layout = QVBoxLayout(self)

        layout.addStretch(1)
        layout.addLayout(self._select_module_text())
        layout.addWidget(self._teaser_text())
        layout.addStretch(1)

        self.setLayout(layout)

    def _select_module_text(self) -> QHBoxLayout:
        h_box = QHBoxLayout()
        h_box.addStretch(1)

        icon_widget = qta.IconWidget()
        icon_widget.setIconSize(QtCore.QSize(36, 36))
        icon_widget.setIcon(ARROW_LEFT_BOLD(color="#4d5157"))

        label = QLabel("Select a module to begin", self)
        label.setStyleSheet("font-size: 20px;")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        h_box.addWidget(icon_widget)
        h_box.addWidget(label)
        h_box.addStretch(1)

        return h_box

    def _teaser_text(self) -> QLabel:
        teaser_label = QLabel(
            "More detectors and example applications will\nbe released continuously.", self
        )
        teaser_label.setStyleSheet("font-size: 16px;")
        teaser_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        return teaser_label

    def handle_message(self, message: Any) -> None:
        pass

    def draw(self) -> None:
        pass


class PluginPlotArea(QFrame):
    _FPS = 60

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.plot_plugin: PlotPluginBase = PlotPlaceholder(app_model)

        self.setObjectName("PluginPlotArea")
        self.setStyleSheet("QFrame#PluginPlotArea {background: #fff; border: 0;}")
        self.setFrameStyle(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.plot_plugin)

        self.startTimer(int(1000 / self._FPS))

        app_model.sig_load_plugin.connect(self._on_app_model_load_plugin)
        if isinstance(app_model.plugin, PluginSpecBase):
            self._on_app_model_load_plugin(app_model.plugin)
        elif app_model.plugin is not None:
            msg = f"{type(app_model.plugin)} is not a PluginSpecBase."
            raise RuntimeError(msg)

        self.setLayout(layout)

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        plugin_class_name = type(self.plot_plugin).__name__
        with self.app_model.report_timing(f"{plugin_class_name}.draw()"):
            self.plot_plugin.draw()

    def _on_app_model_load_plugin(self, plugin: Optional[PluginSpecBase]) -> None:
        log.debug(
            f"{self.__class__.__name__} is going to replace its plot_plugin "
            + f"({self.plot_plugin.__class__.__name__}) in favour of {plugin}"
        )
        self.plot_plugin.deleteLater()

        if plugin is None:
            self.plot_plugin = PlotPlaceholder(self.app_model)
        else:
            self.plot_plugin = plugin.create_plot_plugin(app_model=self.app_model)

        layout = self.layout()
        assert layout is not None
        layout.addWidget(self.plot_plugin)


class ControlPlaceholder(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QGridLayout(self)

        with as_file(files(resources) / "icon-black.svg") as path:
            icon = QSvgWidget(str(path), self)

        icon.setMaximumSize(60, 60)
        icon.renderer().setAspectRatioMode(QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        effect = QGraphicsOpacityEffect(icon)
        effect.setOpacity(0.1)
        icon.setGraphicsEffect(effect)

        layout.addWidget(icon)
        self.setLayout(layout)


class PluginControlArea(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model
        self.app_model.sig_load_plugin.connect(self._on_app_model_load_plugin)

        self.child_widget: QWidget = ControlPlaceholder()
        self.view_plugin: Optional[Any] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.child_widget)

        if isinstance(app_model.plugin, PluginSpecBase):
            self._on_app_model_load_plugin(app_model.plugin)
        elif app_model.plugin is not None:
            msg = f"{type(app_model.plugin)} is not a PluginSpecBase."
            raise RuntimeError(msg)
        self.setLayout(layout)

    def _on_app_model_load_plugin(self, plugin_spec: Optional[PluginSpecBase]) -> None:
        log.debug(
            f"{self.__class__.__name__} is going to replace its view_plugin"
            + f"({self.view_plugin.__class__.__name__}) in favour of {plugin_spec}"
        )
        self.view_plugin = None
        self.child_widget.deleteLater()

        if plugin_spec is None:
            self.child_widget = ControlPlaceholder()
        else:
            self.child_widget = plugin_spec.create_view_plugin(
                app_model=self.app_model,
            )

        layout = self.layout()
        assert layout is not None
        layout.addWidget(self.child_widget)
