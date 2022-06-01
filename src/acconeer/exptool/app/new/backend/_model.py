from __future__ import annotations

from typing import Optional

from acconeer.exptool.app.new.plugin import BackendPlugin, Plugin


class Model:
    def __init__(self) -> None:
        self.backend_plugin: Optional[BackendPlugin] = None

    def execute_task(self, task):
        method_name, kwargs = task
        method = getattr(self, "_" + method_name)
        method(**kwargs)

    def _plugin_callback(self, *args, **kwargs):
        pass

    def _load_plugin(self, *, plugin: Plugin) -> None:
        self.backend_plugin = plugin.backend_plugin()
        self.backend_plugin.setup(callback=self._plugin_callback)
