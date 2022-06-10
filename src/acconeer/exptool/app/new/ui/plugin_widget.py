from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget

import pyqtgraph as pg

from acconeer.exptool.app.new import interactions, utils
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin import Plugin


class PluginControlWidget(QWidget):
    def __init__(
        self,
        app_model: AppModel,
        plot_layout_widget: pg.GraphicsLayoutWidget,
        plugins: list[Plugin],
        *,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.app_model = app_model

        layout = QVBoxLayout(self)
        self.plugin_dropdown = QComboBox()
        self.plugin_dropdown.addItem("Select an application")
        self.update_plugins_list(plugins)
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
