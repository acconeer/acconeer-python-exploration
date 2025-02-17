# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved
from __future__ import annotations

import argparse
import ctypes
import functools
import logging
import re
import sys
import time
import typing as t
from importlib.resources import as_file, files

import qdarktheme

from PySide6 import QtCore, QtGui
from PySide6.QtWidgets import QApplication

import pyqtgraph as pg

from acconeer.exptool.app import resources
from acconeer.exptool.utils import config_logging

from ._enums import ConnectionState, PluginGeneration, PluginState
from .app_model import AppModel
from .backend import Backend, GenBackend, MpBackend
from .plugin_loader import import_and_register_plugin_module, load_plugins
from .storage import remove_config_dir, remove_temp_dir
from .ui.app_model_viewer import AppModelViewer
from .ui.main_window import MainWindow


_LOG = logging.getLogger(__name__)


def main() -> None:
    parser = _ExptoolArgumentParser()
    args = parser.parse_args()
    config_logging(args)

    if args.tasks:
        any_autoconnect = (
            args.usb_or_serial_autoconnect
            or args.simulated_autoconnect
            or args.socket_autoconnect is not None
        )
        if not any_autoconnect:
            parser.print_usage()
            print("ERROR: One of the 'autoconnect' options are required when using '--tasks'")
            sys.exit(1)

        if args.plugin_key is None:
            parser.print_usage()
            print("ERROR: The '--plugin-key' option is required when using '--tasks'")
            sys.exit(1)

    if args.purge_cache:
        remove_config_dir()
        remove_temp_dir()
        print("Cache purged")
        sys.exit(0)

    if sys.platform == "win32" or sys.platform == "cygwin":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("acconeer.exptool")

    if QApplication.instance() is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
        )

    # The cast necessitated of a miss in the typing stubs.
    app: QApplication = t.cast(QApplication, QApplication.instance()) or QApplication(sys.argv)

    # Make sure to wrap urls in single quotation marks to avoid errors parsing stylesheet
    stylesheet = qdarktheme.load_stylesheet("light")
    search_pattern = r"url\((.*?)\)"
    replace_pattern = r"url('\1')"
    stylesheet = re.sub(search_pattern, replace_pattern, stylesheet)

    app.setStyleSheet(stylesheet)
    app.setAttribute(QtCore.Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)

    if args.plugin_modules is not None:
        for plugin_module_name in args.plugin_modules:
            import_and_register_plugin_module(plugin_module_name)

    plugins = load_plugins()
    plugin_keys = [p.key for p in plugins]

    if args.plugin_key is not None and args.plugin_key not in plugin_keys:
        parser.print_usage()
        print(f"ERROR: Could not find plugin with key {args.plugin_key!r}")
        print(f"ERROR: Available plugin keys: {plugin_keys}")
        sys.exit(1)

    backend: Backend
    if args.same_process:
        backend = GenBackend()
    else:
        backend = MpBackend()
    backend.start()

    model = AppModel(
        backend,
        plugins,
        args.usb_or_serial_autoconnect,
        args.socket_autoconnect,
        args.simulated_autoconnect,
    )
    model.start()

    app.aboutToQuit.connect(model.stop)
    app.aboutToQuit.connect(backend.stop)

    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOption("leftButtonPan", False)
    pg.setConfigOptions(antialias=True)

    with as_file(files(resources) / "icon.png") as path:
        app.setWindowIcon(_pixmap_to_icon(QtGui.QPixmap(str(path))))

    mw = MainWindow(model)
    mw.show()

    if args.amv:
        app_model_viewer = AppModelViewer(model)
        app_model_viewer.show()
        mw.sig_closing.connect(app_model_viewer.close)

    specified_generation = PluginGeneration[args.generation_str.upper()]
    model.set_plugin_generation(specified_generation)

    if args.plugin_key is not None:
        found_plugin = model.find_plugin(args.plugin_key, specified_generation)

        if found_plugin is None:
            _LOG.warning(f"Could not find plugin with key {args.plugin_key!r}")
        else:
            if args.tasks:
                tasks = tuple(str(t) for t in args.tasks)

                model.sig_notify.connect(
                    functools.partial(
                        _send_startup_tasks, tasks=tasks, deadline=time.monotonic() + 5
                    ),
                    QtCore.Qt.ConnectionType.SingleShotConnection,
                )

            model.load_plugin(found_plugin)

    model.broadcast()

    sys.exit(app.exec())


def _send_startup_tasks(app_model: AppModel, tasks: tuple[str, ...], deadline: float) -> None:
    """Uses tail-end recursion to offer passed 'tasks' once the app
    is in the correct state
    """
    if not tasks:
        _LOG.info("No more tasks to run.")
        return

    seconds_left = deadline - time.monotonic()
    if seconds_left < 0:
        _LOG.warning(f"Startup tasks timed out. Giving up on tasks {list(tasks)}.")
        return

    (task_to_send, *rest_of_tasks) = tasks

    def _on_error(exception: Exception, traceback_format_exc: t.Optional[str] = None) -> None:
        _LOG.warning(
            f"Startup tasks that won't execute due to the failure of {task_to_send!r}: {rest_of_tasks}"
        )
        app_model.emit_error(exception, traceback_format_exc)

    def _retry() -> None:
        app_model.sig_notify.connect(
            functools.partial(_send_startup_tasks, tasks=tasks, deadline=deadline),
            QtCore.Qt.ConnectionType.SingleShotConnection,
        )

    retry_str = f"Retrying ... ({seconds_left:.2f}s left)"

    if app_model.connection_state is not ConnectionState.CONNECTED:
        _LOG.info(f"Cannot execute {task_to_send!r}: No sensor connected yet. {retry_str}")
        _retry()
    elif app_model.plugin_state.is_busy:
        _LOG.info(f"Cannot execute {task_to_send!r}: Plugin is busy. {retry_str}")
        _retry()
    elif app_model.plugin_state is not PluginState.LOADED_IDLE:
        _LOG.info(f"Cannot execute {task_to_send!r}: No plugin loaded yet. {retry_str}")
        _retry()
    else:
        _LOG.info(f"Executing {task_to_send!r} ...")
        app_model.put_task(
            (task_to_send, {}),
            on_ok=lambda: _send_startup_tasks(app_model, tuple(rest_of_tasks), deadline),
            on_error=_on_error,
        )


class _ExptoolArgumentParser(argparse.ArgumentParser):
    def __init__(self) -> None:
        super().__init__(prog="python -m acconeer.exptool.app.new")

        self.add_argument(
            "--purge-cache",
            "--purge-config",
            action="store_true",
            help="Remove cache files.",
        )
        self.add_argument(
            "--portable",
            action="store_true",
            help=argparse.SUPPRESS,  # makes option hidden
        )

        plugin_group = self.add_argument_group(title="plugins")
        plugin_group.add_argument(
            "--plugin-module",
            dest="plugin_modules",
            metavar="module",
            action="append",  # "append" => --plugin-module X --plugin-module Y => [X, Y]
            help=(
                "Allows you to load an arbitrary plugin given a python module "
                + "(installed or in your working directory) NOTE! Accepted argument "
                + "is not a path (e.g. not 'my_processor/latest/plugin.py'), it's a "
                + "python module (e.g. 'my_processor.latest.plugin'). "
                + "This option can be repeated."
            ),
        )

        startup_group = self.add_argument_group(title="startup")
        connect_group = startup_group.add_mutually_exclusive_group()
        connect_group.add_argument(
            "--autoconnect",
            dest="usb_or_serial_autoconnect",
            action="store_true",
            help="Enable the auto connect feature for USB or serial devices.",
        )
        connect_group.add_argument(
            "--socket-autoconnect",
            metavar="ip",
            help="Connect to 'ip' on startup.",
        )
        connect_group.add_argument(
            "--simulated-autoconnect",
            action="store_true",
            help="Connect to the sensor simulation at startup.",
        )
        startup_group.add_argument(
            "--plugin-key",
            dest="plugin_key",
            metavar="key",
            type=str,
            help="Load the plugin with given key on startup. E.g. 'sparse_iq' or 'distance_detector'.",
        )
        startup_group.add_argument(
            "--generation",
            dest="generation_str",
            choices=[PluginGeneration.A121.value],
            default="a121",
            type=str,
            help="Generation that is selected on startup. Also used in conjunction with '--plugin-key' to find plugins.",
        )
        startup_group.add_argument(
            "--tasks",
            nargs="+",
            default=[],
            help=(
                "A chain of zero-argument backend tasks ('@is_task') to execute at startup, "
                + "e.g. 'start_session' or 'calibrate_detector start_session'. "
                + "If you run into issues, turn on verbose logs ('-v') for more information."
            ),
        )

        dbg_group = self.add_argument_group(title="debugging")
        dbg_group.add_argument(
            "--same-process",
            action="store_true",
            help="Run the application backend in the main thread. Deteriorates performance but enables backend plugin debugging (e.g. with breakpoint())",
        )
        dbg_group.add_argument(
            "--amv",
            action="store_true",
            help="Start the AppModelViewer alongside Exploration Tool",
        )

        verbosity_group = self.add_mutually_exclusive_group(required=False)
        verbosity_group.add_argument(
            "-v",
            "--verbose",
            action="store_true",
        )
        verbosity_group.add_argument(
            "-vv",
            "--debug",
            action="store_true",
        )
        verbosity_group.add_argument(
            "-q",
            "--quiet",
            action="store_true",
        )


def _pixmap_to_icon(pixmap: QtGui.QPixmap) -> QtGui.QIcon:
    size = max(pixmap.size().height(), pixmap.size().width())

    square_pixmap = QtGui.QPixmap(size, size)
    square_pixmap.fill(QtGui.QRgba64.fromRgba(0, 0, 0, 0))

    painter = QtGui.QPainter(square_pixmap)
    painter.drawPixmap(
        (square_pixmap.size().width() - pixmap.size().width()) // 2,
        (square_pixmap.size().height() - pixmap.size().height()) // 2,
        pixmap,
    )
    painter.end()

    scaled_pixmap = square_pixmap.scaled(
        256,
        256,
        aspectMode=QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        mode=QtGui.Qt.TransformationMode.SmoothTransformation,
    )

    return QtGui.QIcon(scaled_pixmap)
