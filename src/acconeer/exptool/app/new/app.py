# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved
from __future__ import annotations

import argparse
import ctypes
import faulthandler
import functools
import logging
import os
import re
import signal
import sys
import threading
import time
import traceback
import typing as t
from pathlib import Path

from acconeer.exptool._processes.start_method import avoid_fork
from acconeer.exptool.app.install_missing_app_extra import INSTALL_MISSING_APP_EXTRA_INSTRUCTIONS
from acconeer.exptool.utils import config_logging


try:
    import qdarktheme

    from PySide6 import QtCore
    from PySide6.QtWidgets import QApplication, QMessageBox

    import pyqtgraph as pg

    # Imports bs4, which comes with the app extra
    from acconeer.exptool._artifact_repository import (
        ArtifactRepositoryError,
        create_artifact_repository,
        describe_algo_bundle,
        load_plugin_file,
    )
    from acconeer.exptool.app.desktop_integration import (
        ensure_wayland_integration,
        set_app_id,
        set_window_class_icon,
    )
except ImportError:
    traceback.print_exc(file=sys.stdout)
    print(INSTALL_MISSING_APP_EXTRA_INSTRUCTIONS)
    sys.exit(1)


from ._enums import ConnectionState, PluginGeneration
from ._sigint import _InterruptCounter
from .app_model import AppModel, PluginSpec
from .backend import Backend, GenBackend, MpBackend
from .plugin_loader import import_and_register_plugin_module, load_plugins
from .storage import (
    DEFAULT_ET_DIR,
    get_algo_bundle_path,
    remove_config_dir,
    remove_temp_dir,
    set_et_dir,
)
from .ui.app_model_viewer import AppModelViewer
from .ui.main_window import MainWindow


_LOG = logging.getLogger(__name__)

# Budget for the app to connect, load the requested plugin, and reach a
# state where it can run the '--tasks' chain. Starts before app.exec(), so
# it also has to absorb QApplication/MainWindow construction and plugin
# discovery, not just in-event-loop retries.
_STARTUP_TASKS_TIMEOUT_S = 20.0
_STARTUP_TASKS_GIVE_UP_EXIT_CODE = 2

_QUIT_PRESS_COUNT = 3
_QUIT_WINDOW_S = 5.0
_QUIT_MIN_GAP_S = 0.3


def main() -> None:
    parser = _ExptoolArgumentParser()
    args = _parse_args(parser)
    config_logging(args)
    avoid_fork(preload=["acconeer.exptool.app.new.backend"])

    # Dump a C + Python stack trace on native crashes (segfaults) that bypass
    # Python's excepthook and exit silently. Writes via async-signal-safe fd
    # writes, so it survives a crash that would discard buffered stderr/logging.
    faulthandler.enable()

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

    if args.data_dir_override is not None:
        set_et_dir(args.data_dir_override)

    if args.artifact_repository is not None:
        try:
            load_plugin_file(args.artifact_repository)
            # Fails fast on a broken plugin, rather than when flashing.
            create_artifact_repository()
        except ArtifactRepositoryError as e:
            parser.error(str(e))

    if sys.platform == "win32" or sys.platform == "cygwin":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("acconeer.exptool")

    if QApplication.instance() is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
        )
        QApplication.setAttribute(QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        set_app_id()

    # Silences noisy, harmless focus-tracking mismatches logged by Qt's
    # Wayland text-input integration (zwp_text_input_v3).
    QtCore.QLoggingCategory.setFilterRules("qt.qpa.wayland.textinput=false")

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

    if args.plugin_key is not None and args.generation_str is None:
        parser.print_usage()
        print("ERROR: Must specify '--generation' when specifying '--plugin-key'.")
        sys.exit(1)

    backend: Backend
    if args.same_process:
        backend = GenBackend()
    else:
        backend = MpBackend()

    model, mw = build_main_window(args, plugins, backend)
    app.aboutToQuit.connect(model.stop)
    app.aboutToQuit.connect(backend.stop)

    install_startup_algo_bundle(args, model)

    if args.amv:
        app_model_viewer = AppModelViewer(model)
        app_model_viewer.show()
        mw.sig_closing.connect(app_model_viewer.close)

    load_startup_plugin(args, model)

    py_ver = sys.version_info[:2]
    if args.portable and py_ver < (3, 12):
        # Note: Only users with old 3.9 portable package will see this message
        msg = "\n".join(
            [
                "This ET distribution is discontinued.",
                "<br><br>",
                "Download the new QUICK INSTALL package from",
                "<a href='https://developer.acconeer.com/home/exploration-tool/'>developer.acconeer.com</a>",
                "<br><br>",
                "Feel free to continue using this distribution of ET, but note that it is incompatible with future versions of ET",
            ]
        )
        qmb = QMessageBox()
        qmb.setWindowTitle("Discontinuation notice")
        qmb.setTextFormat(QtCore.Qt.TextFormat.RichText)
        qmb.setText(msg)
        qmb.setIcon(QMessageBox.Icon.Information)
        qmb.exec()

    model.broadcast()

    sys.excepthook = model.excepthook

    # Allow quitting by pressing Ctrl+C in the launching terminal, repeated
    # _QUIT_PRESS_COUNT times within _QUIT_WINDOW_S seconds. _QUIT_MIN_GAP_S
    # keeps a single held-down press (which auto-repeats) from being counted
    # as several. app.quit() exits the event loop, triggering the aboutToQuit
    # teardown wired above (model.stop / backend.stop). A watchdog
    # force-exits if that teardown hangs.
    shutdown_complete = threading.Event()
    interrupts = _InterruptCounter(window_s=_QUIT_WINDOW_S, min_gap_s=_QUIT_MIN_GAP_S)

    def _sigint_handler(*_: t.Any) -> None:
        presses = min(interrupts.press(now=time.monotonic()), _QUIT_PRESS_COUNT)
        progress = f"({presses}/{_QUIT_PRESS_COUNT})"

        # Flushed explicitly: this feedback is the whole point of the press count,
        # and stdout is block buffered whenever the app's output is piped.
        if presses < _QUIT_PRESS_COUNT:
            print(f"\nCtrl+C received {progress}", flush=True)
            return

        print(f"\nCtrl+C received {progress}, shutting down...", flush=True)

        def _watchdog() -> None:
            if not shutdown_complete.wait(2.0):
                print("forcing exit...", flush=True)
                os._exit(1)

        threading.Thread(target=_watchdog, daemon=True).start()
        app.quit()

    signal.signal(signal.SIGINT, _sigint_handler)

    # A no-op timer periodically returns control to the Python interpreter so the
    # SIGINT handler can run while the Qt event loop is active.
    sigint_timer = QtCore.QTimer()
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(200)

    exit_code = app.exec()
    shutdown_complete.set()
    sys.exit(exit_code)


def build_main_window(
    args: argparse.Namespace, plugins: list[PluginSpec], backend: Backend
) -> tuple[AppModel, MainWindow]:
    """Starts ``backend`` and shows a main window on a new model of it.

    Unlike main(), leaves the process's signal handling, exception hook and exit
    alone, so that the app can also be built inside a test.
    """
    backend.start()

    model = create_app_model(args, plugins, backend)
    model.start()

    if args.dump_exceptions:
        model.sig_error.connect(lambda _, traceback_str: print(traceback_str, sep="\n"))

    pg.setConfigOption("background", "w")
    pg.setConfigOption("foreground", "k")
    pg.setConfigOption("leftButtonPan", False)
    pg.setConfigOptions(antialias=True)

    app = QApplication.instance()
    assert isinstance(app, QApplication)
    icon = ensure_wayland_integration(app)

    mw = MainWindow(model)
    set_window_class_icon(mw, icon)
    mw.show()
    return model, mw


def create_app_model(
    args: argparse.Namespace, plugins: list[PluginSpec], backend: Backend
) -> AppModel:
    return AppModel(
        backend,
        plugins,
        args.use_port_updater,
        args.usb_or_serial_autoconnect,
        args.socket_autoconnect,
        args.simulated_autoconnect,
        PluginGeneration[args.generation_str.upper()] if args.generation_str is not None else None,
        algo_bundle=args.algo_bundle or get_algo_bundle_path(),
        skip_integrity_check=args.dangerously_skip_integrity_check,
    )


def install_startup_algo_bundle(args: argparse.Namespace, model: AppModel) -> None:
    if model.algo_bundle.is_file():
        if args.dangerously_skip_integrity_check:
            _warn_of_skipped_integrity_check(model.algo_bundle)
        model.try_install_algo_bundle()


def _warn_of_skipped_integrity_check(zip_path: Path) -> None:
    _LOG.warning(
        f"Skipping the integrity check of the algo bundle {describe_algo_bundle(zip_path)}"
    )


def _algo_bundle_file(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        msg = f"No algo bundle at '{path}'"
        raise argparse.ArgumentTypeError(msg)
    return path


def load_startup_plugin(args: argparse.Namespace, model: AppModel) -> None:
    """Loads the plugin given by '--plugin-key', running '--tasks' once it can."""
    if args.generation_str is None:
        return

    specified_generation = PluginGeneration[args.generation_str.upper()]
    model.set_plugin_generation(specified_generation)

    if args.plugin_key is None:
        return

    found_plugin = model.find_plugin(args.plugin_key, specified_generation)
    if found_plugin is None:
        _LOG.warning(f"Could not find plugin with key {args.plugin_key!r}")
        return

    if args.tasks:
        tasks = tuple(str(t) for t in args.tasks)

        model.sig_notify.connect(
            functools.partial(
                _send_startup_tasks,
                tasks=tasks,
                deadline=time.monotonic() + _STARTUP_TASKS_TIMEOUT_S,
            ),
            QtCore.Qt.ConnectionType.SingleShotConnection,
        )

    model.load_plugin(found_plugin)


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
        qapp = QApplication.instance()
        assert qapp is not None
        qapp.exit(_STARTUP_TASKS_GIVE_UP_EXIT_CODE)
        return

    (task_to_send, *rest_of_tasks) = tasks

    def _on_error(exception: Exception, traceback_format_exc: str | None = None) -> None:
        _LOG.warning(
            f"Startup tasks that won't execute due to the failure of {task_to_send!r}: {rest_of_tasks}"
        )
        app_model.emit_error(exception, traceback_format_exc)

    def _retry() -> None:
        app_model.sig_notify.connect(
            functools.partial(_send_startup_tasks, tasks=tasks, deadline=deadline),
            QtCore.Qt.ConnectionType.SingleShotConnection,
        )

    def _put_task_and_continue() -> None:
        _LOG.info(f"Executing {task_to_send!r} ...")
        app_model.put_task(
            (task_to_send, {}),
            on_ok=lambda: _send_startup_tasks(app_model, tuple(rest_of_tasks), deadline),
            on_error=_on_error,
        )

    retry_str = f"Retrying ... ({seconds_left:.2f}s left)"

    if app_model.connection_state is not ConnectionState.CONNECTED:
        _LOG.info(f"Cannot execute {task_to_send!r}: No sensor connected yet. {retry_str}")
        _retry()
    elif not app_model.plugin_state.is_loaded:
        _LOG.info(f"Cannot execute {task_to_send!r}: No plugin loaded yet. {retry_str}")
        _retry()

    # BEGIN Tasks that are allowed while busy (& not busy)
    elif task_to_send == "stop_session":
        _put_task_and_continue()
    # END Tasks that are allowed while busy (& not busy)

    elif app_model.plugin_state.is_busy:
        _LOG.info(f"Cannot execute {task_to_send!r}: Plugin is busy. {retry_str}")
        _retry()

    # BEGIN Tasks that are allowed only while not busy
    elif task_to_send == "pseudo:quit":
        qapp = QApplication.instance()
        assert qapp is not None
        _LOG.info("Executing 'pseudo:quit' ...")
        qapp.processEvents()
        qapp.exit(app_model.num_errors)
    else:
        _put_task_and_continue()
    # END Tasks that are allowed only while not busy


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

        # A pluggy plugin file providing the repository the flash wizard
        # downloads images from, instead of the developer site. Internal use only.
        self.add_argument(
            "--artifact-repository",
            dest="artifact_repository",
            help=argparse.SUPPRESS,  # makes option hidden
        )

        # An algo bundle zip used instead of the one downloaded from the
        # artifact repository. Internal use only. Also read from
        # ET_ALGO_BUNDLE, which this option overrides.
        self.add_argument(
            "--algo-bundle",
            type=_algo_bundle_file,
            help=argparse.SUPPRESS,  # makes option hidden
        )
        # Installs the algo bundle of this launch without checking that this
        # release expects it. Internal use only.
        self.add_argument(
            "--dangerously-skip-integrity-check",
            action="store_true",
            help=argparse.SUPPRESS,  # makes option hidden
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
            choices=[PluginGeneration.A121.value, PluginGeneration.A2.value],
            default=None,
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
        dbg_group.add_argument(
            "--dump-exceptions",
            action="store_true",
            help="Prints exceptions caught in the application to stdout",
        )
        dbg_group.add_argument(
            "--no-port-updater",
            action="store_false",
            dest="use_port_updater",
            help="Disable port (Serial/USB) discovery, limiting server connections socket (and simulated)",
        )
        dbg_group.add_argument(
            "--data-dir",
            dest="data_dir_override",
            type=Path,
            help=f"Set directory to use for data (data is saved to '{DEFAULT_ET_DIR}' by default)",
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


def _parse_args(
    parser: argparse.ArgumentParser, argv: list[str] | None = None
) -> argparse.Namespace:
    args = parser.parse_args(argv)
    env_bundle = os.environ.get("ET_ALGO_BUNDLE")
    if args.algo_bundle is None and env_bundle:
        try:
            args.algo_bundle = _algo_bundle_file(env_bundle)
        except argparse.ArgumentTypeError as e:
            parser.error(f"{e}, which ET_ALGO_BUNDLE points to")
    return args
