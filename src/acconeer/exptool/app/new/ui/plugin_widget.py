from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg

from acconeer.exptool.app.new import interactions, utils
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin import Plugin, PluginFamily


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
        self.button_group.buttonClicked.connect(self._on_click)

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

    def _on_click(self):
        plugin = self.button_group.checkedButton().plugin
        self.app_model.load_plugin(plugin)

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


class PluginControlWidget(QWidget):
    def __init__(
        self,
        app_model: AppModel,
        plot_layout_widget: pg.GraphicsLayoutWidget,
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.app_model = app_model

        layout = QVBoxLayout(self)
        self.plugin_dropdown = QComboBox()
        self.plugin_dropdown.addItem("Select an application")
        self.update_plugins_list(app_model.plugins)
        layout.addWidget(self.plugin_dropdown)

        self.lended_control_widget = QWidget()
        layout.addWidget(self.lended_control_widget)

        self.lended_plot_layout_widget = plot_layout_widget

        self.plugin_dropdown.currentIndexChanged.connect(self.on_dropdown_change)
        self.setLayout(layout)

    def update_plugins_list(self, plugins: list[Plugin]) -> None:
        while self.plugin_dropdown.count() > 1:
            self.plugin_dropdown.removeItem(1)

        for plugin in plugins:
            self.plugin_dropdown.addItem(plugin.key, plugin)

    def on_dropdown_change(self) -> None:
        self.tear_down_plugin()

        label = self.plugin_dropdown.currentText()
        if label == "Select a service":
            return

        _ = self.plugin_dropdown.currentData()

    def handle_plugin_setup_response(self, response: interactions.Response) -> None:
        if response.error:
            utils.show_error_pop_up(
                "Plugin setup error",
                response.error.message,
            )

    def tear_down_plugin(self) -> None:
        self.lended_plot_layout_widget.ci.clear()
        for child in self.lended_control_widget.children():
            child.deleteLater()
