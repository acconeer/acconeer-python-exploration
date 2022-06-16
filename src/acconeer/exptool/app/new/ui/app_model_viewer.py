from PySide6.QtWidgets import QTextEdit

from acconeer.exptool.app.new.app_model import AppModel


class AppModelViewer(QTextEdit):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__()
        app_model.sig_notify.connect(self._update_text)
        self.setFontFamily("monospace")
        self.setFixedSize(500, 200)
        self.setReadOnly(True)

    def _update_text(self, app_model: AppModel) -> None:
        self.setText(
            "\n".join(
                [
                    "=== AppModel ===",
                    "",
                    f"ConnectionState:        {app_model.connection_state}",
                    f"ConnectionInterface:    {app_model.connection_interface}",
                    f"PluginState:            {app_model.plugin_state}",
                    f"socket_connection_ip:   {app_model.socket_connection_ip}",
                    f"serial_connection_port: {app_model.serial_connection_port}",
                ]
            )
        )
