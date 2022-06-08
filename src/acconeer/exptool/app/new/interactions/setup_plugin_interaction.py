from typing import Any

from acconeer.exptool.a121._core import SensorConfig
from acconeer.exptool.app.new.app_model import AppModel
from acconeer.exptool.app.new.plugin import Plugin

from .response import Error, Response, Success


def setup_plugin(
    plugin: Plugin,
    app_model: AppModel,
    view_widget: Any,
    plot_widget: Any,
) -> Response[None]:
    if plugin is None:
        return Error(plugin, None, "Passed plugin was None.")

    error = _setup_view_plugin(plugin, view_widget, app_model).error
    if error:
        return error

    error = _setup_plot_plugin(plugin, plot_widget).error
    if error:
        return error

    error = _setup_backend_plugin(plugin, app_model).error
    if error:
        return error

    return Success(plugin, None, None)


def _setup_view_plugin(plugin: Plugin, view_widget: Any, app_model: AppModel) -> Response[None]:
    try:
        view_plugin = plugin.view_plugin(  # type: ignore[call-arg]
            app_model=app_model, parent=view_widget
        )
        view_plugin.setup()
    except Exception as e:
        return Error(None, None, f"Could not setup view plugin: {e}")
    else:
        return Success(view_plugin, None, None)


def _setup_plot_plugin(plugin: Plugin, plot_widget: Any) -> Response[None]:
    try:
        plot_plugin = plugin.plot_plugin(  # type: ignore[call-arg]
            SensorConfig(), parent=plot_widget  # FIXME: do not hardcode of SensorConfig.
        )
        plot_plugin.setup()
    except Exception as e:
        return Error(None, None, f"Could not setup plot plugin: {e}")
    else:
        return Success(plot_plugin, None, None)


def _setup_backend_plugin(plugin: Plugin, app_model: AppModel) -> Response[None]:
    backend_plugin = plugin.backend_plugin()
    _ = backend_plugin
    # TODO: backend.load_plugin(backend_plugin)

    return Success(backend_plugin, None, None)
