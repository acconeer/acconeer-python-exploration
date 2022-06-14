from __future__ import annotations

from typing import Optional

from PySide6 import QtCore
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool.app.new.app_model import (
    AppModel,
    PlotPlugin,
    Plugin,
    PluginFamily,
    ViewPlugin,
)


class PluginSelectionButton(QPushButton):
    plugin: Plugin

    def __init__(self, plugin: Plugin, parent: QWidget) -> None:
        super().__init__(parent)

        self.plugin = plugin

        self.setText(plugin.title)
        self.setStyleSheet("text-align: left; font-weight: bold;")
        self.setCheckable(True)


class PluginSelectionButtonGroup(QButtonGroup):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setExclusive(True)

    def addButton(self, button: PluginSelectionButton) -> None:
        super().addButton(button)

    def checkedButton(self) -> PluginSelectionButton:
        button = super().checkedButton()
        assert isinstance(button, PluginSelectionButton)
        return button

    def buttons(self) -> list[PluginSelectionButton]:
        buttons = super().buttons()
        assert isinstance(buttons, list)
        assert all(isinstance(e, PluginSelectionButton) for e in buttons)
        return buttons


class PluginSelection(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        app_model.sig_notify.connect(self._on_app_model_update)

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(11)

        group_boxes = {}
        for family in PluginFamily:
            group_box = QGroupBox(self)
            group_box.setTitle(family.value)
            group_box.setHidden(True)
            group_box.setLayout(QVBoxLayout(group_box))
            self.layout().addWidget(group_box)
            group_boxes[family] = group_box

        self.button_group = PluginSelectionButtonGroup(self)
        self.button_group.buttonClicked.connect(self._on_load_click)

        for plugin in app_model.plugins:
            group_box = group_boxes[plugin.family]
            group_box.setHidden(False)

            button = PluginSelectionButton(plugin, group_box)
            self.button_group.addButton(button)
            group_box.layout().addWidget(button)

            if plugin.description:
                label = QLabel(group_box)
                label.setText(plugin.description)
                label.setWordWrap(True)
                group_box.layout().addWidget(label)

        self.unload_button = QPushButton("Deselect", self)
        self.unload_button.setStyleSheet("text-align: left;")
        self.unload_button.setFlat(True)
        self.unload_button.clicked.connect(self._on_unload_click)
        self.layout().addWidget(self.unload_button)

    def _on_load_click(self):
        plugin = self.button_group.checkedButton().plugin
        self.app_model.load_plugin(plugin)

    def _on_unload_click(self):
        self.app_model.load_plugin(None)

    def _on_app_model_update(self, app_model: AppModel) -> None:
        plugin: Optional[Plugin] = app_model.plugin

        if plugin is None:
            self.button_group.setExclusive(False)

            for button in self.button_group.buttons():
                button.setChecked(False)

            self.button_group.setExclusive(True)
        else:
            buttons = self.button_group.buttons()
            button = next(b for b in buttons if b.plugin == plugin)
            button.setChecked(True)

        self.unload_button.setEnabled(plugin is not None)


class PluginPlotArea(QWidget):
    _FPS = 60

    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        self.plot_plugin: Optional[PlotPlugin] = None

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        self.graphics_layout_widget = pg.GraphicsLayoutWidget(self)
        self.layout().addWidget(self.graphics_layout_widget)

        app_model.sig_load_plugin.connect(self._on_app_model_load_plugin)

        self.startTimer(int(1000 / self._FPS))

    def timerEvent(self, event: QtCore.QTimerEvent) -> None:
        if self.plot_plugin is None:
            return

        self.plot_plugin.draw()

    def _on_app_model_load_plugin(self, plugin: Optional[Plugin]) -> None:
        if self.plot_plugin is not None:
            # TODO: teardown
            self.plot_plugin = None

        if plugin is not None:
            self.plot_plugin = plugin.plot_plugin(
                app_model=self.app_model,
                plot_layout=self.graphics_layout_widget,
            )


class PluginControlArea(QWidget):
    def __init__(self, app_model: AppModel, parent: QWidget) -> None:
        super().__init__(parent)

        self.app_model = app_model

        app_model.sig_load_plugin.connect(self._on_app_model_load_plugin)

        self.view_plugin: Optional[ViewPlugin] = None

        self.setLayout(QHBoxLayout(self))

        placeholder_label = QLabel(self)
        self.layout().addWidget(placeholder_label)
        placeholder_label.setText("Plugin control placeholder")

    def _on_app_model_load_plugin(self, plugin: Optional[Plugin]) -> None:
        if self.view_plugin is not None:
            # TODO: teardown
            self.view_plugin = None

        if plugin is not None:
            self.view_plugin = plugin.view_plugin(
                app_model=self.app_model,
                view_widget=self,
            )
