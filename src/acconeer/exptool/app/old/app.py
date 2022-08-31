# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import importlib.resources
import json
import logging
import os
import pathlib
import signal
import sys
import threading
import time
import traceback
import warnings
import webbrowser
from typing import Any, Optional, Tuple

import numpy as np
from packaging import version

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QWidget,
)

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool.a111 import _conf_to_rss_sdk
from acconeer.exptool.a111.algo import Calibration, ModuleInfo
from acconeer.exptool.app import resources

import platformdirs

from . import data_processing
from .elements.helper import (
    CalibrationStatus,
    CalibrationUiState,
    Count,
    ExptoolArgumentParser,
    LoadState,
)
from .elements.modules import (
    MODULE_INFOS,
    MODULE_KEY_TO_MODULE_INFO_MAP,
    MODULE_LABEL_TO_MODULE_INFO_MAP,
)
from .elements.qt_subclasses import (
    AdvancedSerialDialog,
    BiggerMessageBox,
    CollapsibleSection,
    Label,
    SensorSelection,
    SessionInfoView,
)


if "win32" in sys.platform.lower():
    import ctypes

    myappid = "acconeer.exploration.tool"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

HERE = os.path.dirname(os.path.realpath(__file__))
USER_DATA_DIR = platformdirs.user_data_dir(appname="acconeer_exptool", appauthor="Acconeer AB")
LAST_CONF_FILENAME = os.path.join(USER_DATA_DIR, "last_config.npy")

SELECT_A_SERVICE_TEXT = "Select service or detector"

log = logging.getLogger(__name__)


class GUI(QMainWindow):
    sig_scan = Signal(str, str, object)
    sig_sensor_config_pidget_event = Signal(object)
    sig_processing_config_pidget_event = Signal(object)
    sig_calibration_config_pidget_event = Signal(object)

    def __init__(self, under_test=False, use_last_config=True):
        super().__init__()

        self.under_test = under_test
        self.use_last_config = use_last_config

        self.data = None
        self.data_source = None
        self.client = None
        self.num_recv_frames = 0
        self.num_missed_frames = 0
        self.measured_update_rate_fc = et.utils.FreqCounter()
        self.reset_missed_frame_text_time = None
        self.advanced_process_data = {"use_data": False, "process_data": None}
        self.override_baudrate = None
        self.session_info = None
        self.threaded_scan = None

        self.gui_states = {
            "load_state": LoadState.UNLOADED,
            "server_connected": False,
            "replaying_data": False,
            "scan_is_running": False,
            "has_config_error": False,
            "connection_info": None,
        }

        self.current_data_type = None
        self.current_module_label = None
        self.canvas = None
        self.sensors_available = None
        self.calibration: Optional[Calibration] = None
        self.basic_sensor_param_count = Count()
        self.advanced_sensor_param_count = Count()
        self.control_grid_count = Count()
        self.param_grid_count = Count(2)
        self.sensor_widgets = {}

        self.sig_sensor_config_pidget_event.connect(self.pidget_sensor_config_event_handler)
        self.sig_processing_config_pidget_event.connect(
            self.pidget_processing_config_event_handler
        )
        self.sig_calibration_config_pidget_event.connect(
            self.pidget_calibration_config_event_handler
        )

        self.module_label_to_sensor_config_map = {}
        self.module_label_to_processing_config_map = {}
        self.module_label_to_calibration_config_map = {}
        self.current_module_info: Optional[ModuleInfo] = None
        for mi in MODULE_INFOS:
            if mi.sensor_config_class is not None:
                self.module_label_to_sensor_config_map[mi.label] = mi.sensor_config_class()

                processing_config = self.get_default_processing_config(mi.label)
                self.module_label_to_processing_config_map[mi.label] = processing_config

                if mi.calibration_config_class is not None:
                    calibration_config = mi.calibration_config_class()
                    self.module_label_to_calibration_config_map[mi.label] = calibration_config

        with importlib.resources.path(resources, "icon.png") as path:
            self.setWindowIcon(QIcon(str(path)))

        self.main_widget = QtWidgets.QSplitter(self.centralWidget())
        self.main_widget.setStyleSheet("QSplitter::handle{background: lightgrey}")
        self.main_widget.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.setCentralWidget(self.main_widget)

        self.init_pyqtgraph()
        self.init_labels()
        self.init_textboxes()
        self.init_buttons()
        self.init_dropdowns()
        self.init_checkboxes()
        self.init_sublayouts()
        self.init_panel_scroll_area()
        self.init_statusbar()

        self.calibration_ui_state = CalibrationUiState(
            load_btn=self.buttons["load_calibration"],
            save_btn=self.buttons["save_calibration"],
            clear_btn=self.buttons["clear_calibration"],
            source_text=self.textboxes["calibration_source"],
            status_label=self.labels["calibration_status"],
            auto_apply_cb=self.checkboxes["calibration_auto_apply"],
            apply_btn=self.buttons["apply_calibration"],
        )
        self.sig_scan.connect(
            lambda start_or_stop, *_: self.calibration_ui_state.set_scan_is_running(
                start_or_stop == "start"
            )
        )

        self.init_pidgets()
        self.update_interface()

        self.canvas_widget = QFrame(self.main_widget)
        self.canvas_layout = QtWidgets.QVBoxLayout(self.canvas_widget)

        self.main_widget.addWidget(self.panel_scroll_area)

        self.update_canvas(force_update=True)

        self.resize(1200, 800)
        self.setWindowTitle("Acconeer Exploration GUI")
        self.show()
        self.start_up()
        self.set_gui_state(None, None)

        self.radar = data_processing.DataProcessing()

        timer = QtCore.QTimer(self)
        timer.timeout.connect(self.plot_timer_fun)
        timer.start(15)
        self.plot_queue = []

    def init_pyqtgraph(self):
        pg.setConfigOption("background", "#f0f0f0")
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("leftButtonPan", False)
        pg.setConfigOptions(antialias=True)

    def init_labels(self):
        # key: (text)
        label_info = {
            "sensor": ("Sensor",),
            "sweep_buffer": ("Max buffered frames",),
            "data_source": ("",),
            "stored_frames": ("",),
            "interface": ("Interface",),
            "sweep_info": ("",),
            "measured_update_rate": ("",),
            "data_warnings": ("",),
            "rssver": ("",),
            "libver": (f"Lib {et.__version__.split('+')[0]}",),
            "unsupported_mode": ("Mode not supported by this module",),
            "protocol": ("Protocol",),
            "calibration_status": ("",),
        }

        self.labels = {}
        for key, (text,) in label_info.items():
            lbl = QLabel(self)
            lbl.setText(text)
            self.labels[key] = lbl

        for k in ["data_warnings", "unsupported_mode"]:
            lbl = self.labels[k]
            lbl.setStyleSheet("color: #ff0000")
            lbl.setVisible(False)

    def init_textboxes(self):
        # key: (text)
        textbox_info = {
            "host": ("192.168.1.100", True),
            "sweep_buffer": ("1000", True),
            "stored_frames": ("0", False),
            "calibration_source": ("", True),
        }

        self.textboxes = {}
        for key, (text, enabled) in textbox_info.items():
            self.textboxes[key] = QLineEdit(self)
            self.textboxes[key].setText(text)
            self.textboxes[key].setEnabled(enabled)

        calibration_textbox = self.textboxes["calibration_source"]
        calibration_textbox.setReadOnly(True)
        calibration_textbox.setPlaceholderText("No calibration")

    def init_checkboxes(self):
        # text, status, visible, enabled, function, tooltip
        checkbox_info = {
            "verbose": ("Verbose logging", False, True, True, self.set_log_level, None),
            "calibration_auto_apply": (
                "Auto apply calibration",
                False,
                True,
                True,
                self.set_calibration_auto_apply,
                "When checked, any calibration returned from the processor will automatically\n"
                + "be used. It will not apply the buffered calibration.",
            ),
        }

        self.checkboxes = {}
        for key, (text, status, visible, enabled, fun, tooltip) in checkbox_info.items():
            cb = QCheckBox(text, self)
            cb.setChecked(status)
            cb.setVisible(visible)
            cb.setEnabled(enabled)
            cb.setToolTip(tooltip)
            if fun:
                cb.stateChanged.connect(fun)
            self.checkboxes[key] = cb

    def init_graphs(self):
        if self.current_module_info is None:
            with importlib.resources.path(resources, "icon.png") as path:
                canvas = Label(str(path))

            self.refresh_pidgets()
            return canvas

        canvas = pg.GraphicsLayoutWidget()
        self.reload_pg_updater(canvas=canvas)
        self.refresh_pidgets()

        return canvas

    def reload_pg_updater(self, canvas=None, session_info=None):
        if canvas is None:
            canvas = pg.GraphicsLayoutWidget()
            self.swap_canvas(canvas)

        sensor_config = self.get_sensor_config()
        processing_config = self.get_processing_config()

        if session_info is None:
            client = et.a111.Client(mock=True)
            session_info = client.setup_session(sensor_config, check_config=False)

        if self.current_module_info is None:
            return

        self.service_widget = self.current_module_info.pg_updater(
            sensor_config, processing_config, session_info
        )

        self.service_widget.setup(canvas.ci)

    def init_pidgets(self):
        self.last_sensor_config = None

        for sensor_config in self.module_label_to_sensor_config_map.values():
            sensor_config._event_handlers.add(self.pidget_sensor_config_event_handler)
            pidgets = sensor_config._create_pidgets()

            for pidget in pidgets:
                if pidget is None:
                    continue

                category = pidget.param.category
                if category == et.configbase.Category.ADVANCED:
                    grid = self.advanced_sensor_config_section.grid
                    count = self.advanced_sensor_param_count
                else:
                    grid = self.basic_sensor_config_section.grid
                    count = self.basic_sensor_param_count

                grid.addWidget(pidget, count.val, 0, 1, 2)
                count.post_incr()

        self.last_processing_config = None

        for processing_config in self.module_label_to_processing_config_map.values():
            if processing_config is None:
                continue

            processing_config._event_handlers.add(self.pidget_processing_config_event_handler)
            pidgets = processing_config._create_pidgets()

            for pidget in pidgets:
                if pidget is None:
                    continue

                if pidget.param.category == et.configbase.Category.ADVANCED:
                    grid = self.advanced_processing_config_section.grid
                    count = self.param_grid_count
                else:
                    grid = self.basic_processing_config_section.grid
                    count = self.param_grid_count

                grid.addWidget(pidget, count.val, 0, 1, 2)
                count.post_incr()

        self.last_calibration_config = None

        for calibration_config in self.module_label_to_calibration_config_map.values():
            if calibration_config is None:
                continue

            calibration_config._event_handlers.add(self.pidget_calibration_config_event_handler)
            pidgets = calibration_config._create_pidgets()

            for pidget in pidgets:
                if pidget is None:
                    continue

                grid = self.calibration_config_section.grid
                count = self.param_grid_count

                grid.addWidget(pidget, count.val, 0, 1, 2)
                count.post_incr()

        self.refresh_pidgets()
        self.set_gui_state(None, None)

    def refresh_pidgets(self):
        self.refresh_sensor_pidgets()
        self.refresh_processing_pidgets()
        self.refresh_calibration_pidgets()
        self.update_pidgets_on_event()

    def refresh_sensor_pidgets(self):
        sensor_config = self.get_sensor_config()

        if self.last_sensor_config != sensor_config:
            if self.last_sensor_config is not None:
                self.last_sensor_config._state = et.configbase.Config.State.UNLOADED

            self.last_sensor_config = sensor_config

        if sensor_config is None:
            self.basic_sensor_config_section.setVisible(False)
            self.advanced_sensor_config_section.setVisible(False)
            return

        sensor_config._state = et.configbase.Config.State.LOADED

        has_basic_params = has_advanced_params = False
        for param in sensor_config._get_params():
            if param.visible:
                if param.category == et.configbase.Category.ADVANCED:
                    has_advanced_params = True
                else:
                    has_basic_params = True

        self.basic_sensor_config_section.setVisible(has_basic_params)
        self.advanced_sensor_config_section.setVisible(has_advanced_params)

    def refresh_processing_pidgets(self):
        processing_config = self.get_processing_config()

        if self.last_processing_config != processing_config:
            if self.last_processing_config is not None:
                self.last_processing_config._state = et.configbase.Config.State.UNLOADED

            self.last_processing_config = processing_config

        if processing_config is None:
            self.basic_processing_config_section.hide()
            self.advanced_processing_config_section.hide()
            return

        processing_config._state = et.configbase.Config.State.LOADED

        has_basic_params = has_advanced_params = False
        for param in processing_config._get_params():
            if param.visible:
                if param.category == et.configbase.Category.ADVANCED:
                    has_advanced_params = True
                else:
                    has_basic_params = True

        self.basic_processing_config_section.setVisible(has_basic_params)
        self.advanced_processing_config_section.setVisible(has_advanced_params)

    def refresh_calibration_pidgets(self):
        calibration_config = self.get_calibration_config()

        if self.last_calibration_config != calibration_config:
            if self.last_calibration_config is not None:
                self.last_calibration_config._state = et.configbase.Config.State.UNLOADED

            self.last_calibration_config = calibration_config

        if calibration_config is None:
            self.calibration_config_section.hide()
            return

        calibration_config._state = et.configbase.Config.State.LOADED_READONLY

        self.calibration_config_section.setVisible(True)

    def pidget_sensor_config_event_handler(self, sensor_config):
        if threading.current_thread().name != "MainThread":
            self.sig_sensor_config_pidget_event.emit(sensor_config)
            return

        self.update_pidgets_on_event(sensor_config=sensor_config)

    def pidget_processing_config_event_handler(self, processing_config):
        if threading.current_thread().name != "MainThread":
            self.sig_processing_config_pidget_event.emit(processing_config)
            return

        # Processor
        try:
            if isinstance(self.radar.external, self.current_module_info.processor):
                self.radar.external.update_processing_config(processing_config)
        except AttributeError:
            pass

        # Plot updater
        try:
            self.service_widget.update_processing_config(processing_config)
        except AttributeError:
            pass

        self.update_pidgets_on_event(processing_config=processing_config)

    def pidget_calibration_config_event_handler(self, calibration_config):
        if threading.current_thread().name != "MainThread":
            self.sig_calibration_config_pidget_event.emit(calibration_config)
            return

        if self.current_module_info is None or self.current_module_info.calibration_mapper is None:
            return

        # Sync self.calibration
        calib_mapper = self.current_module_info.calibration_mapper
        updated_calibration = calib_mapper.get_updated_calibration_from_configuration(
            configuration=calibration_config,
            calibration=self.calibration,
        )
        self.calibration = updated_calibration

        # Assumes that an update means that the calibration is modified.
        self.calibration_ui_state.modified = True
        self.update_pidgets_on_event(calibration_config=calibration_config)

    def update_pidgets_on_event(
        self, sensor_config=None, processing_config=None, calibration_config=None
    ):
        if sensor_config is None:
            sensor_config = self.get_sensor_config()

        if processing_config is None:
            processing_config = self.get_processing_config()

        if calibration_config is None:
            calibration_config = self.get_calibration_config()

        if sensor_config is None:
            return

        if hasattr(processing_config, "check_sensor_config"):
            pass_on_alerts = processing_config.check_sensor_config(sensor_config)
        else:
            pass_on_alerts = {
                "processing": [],
                "sensor": [],
            }

        all_alerts = []
        alerts = sensor_config._update_pidgets(additional_alerts=pass_on_alerts["sensor"])
        all_alerts.extend(alerts)

        if processing_config is not None:
            alerts = processing_config._update_pidgets(
                additional_alerts=pass_on_alerts["processing"]
            )
            all_alerts.extend(alerts)

        if calibration_config is not None:
            alerts = calibration_config._update_pidgets()
            all_alerts.extend(alerts)

        has_error = any([a.severity == et.configbase.Severity.ERROR for a in all_alerts])
        self.set_gui_state("has_config_error", has_error)

    def init_dropdowns(self):
        self.module_dd = QComboBox(self)
        modules = {}

        for module_info in MODULE_INFOS:
            if module_info.module_family.value not in modules:
                modules[module_info.module_family.value] = [module_info.label]
            else:
                modules[module_info.module_family.value].append(module_info.label)

        self.init_dropdown_sections(modules)

        self.module_dd.currentIndexChanged.connect(self.clear_application_owned_calibration)
        self.module_dd.currentIndexChanged.connect(self.update_canvas)

        self.interface_dd = QComboBox(self)
        self.interface_dd.addItem("Socket", userData=et.a111.Link.SOCKET)
        self.interface_dd.addItem("Serial", userData=et.a111.Link.UART)
        self.interface_dd.addItem("SPI", userData=et.a111.Link.SPI)
        self.interface_dd.addItem("Simulated", userData="mock")
        self.interface_dd.currentIndexChanged.connect(self.update_interface)

        self.ports_dd = QComboBox(self)
        self.ports_dd.hide()
        self.update_ports()

        self.protocol_dd = QComboBox(self)
        self.protocol_dd.setEnabled(False)
        # protocol_dd items and enabled-flag are dynamically set in update_interface.

    def init_dropdown_sections(self, modules: dict):

        self.module_dd.addItem(SELECT_A_SERVICE_TEXT)

        for k, v in modules.items():
            if k is not None:
                if self.module_dd.count() != 0:
                    self.module_dd.insertSeparator(self.module_dd.count())
                    self.module_dd.addItem(k)
                    item = self.module_dd.model().item(self.module_dd.count() - 1, 0)
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsSelectable)

                self.module_dd.addItems(v)

    def set_multi_sensors(self):
        if self.current_module_info is not None:
            module_multi_sensor_support = self.current_module_info.multi_sensor
        else:
            module_multi_sensor_support = False

        if self.get_gui_state("load_state") == LoadState.LOADED:
            source_sensors = json.loads(self.data.sensor_config_dump)["sensor"]
        else:
            source_sensors = self.sensors_available

        for name in self.sensor_widgets:
            self.sensor_widgets[name].set_multi_sensor_support(
                source_sensors, module_multi_sensor_support
            )

    def set_sensors(self, sensors):
        for name in self.sensor_widgets:
            self.sensor_widgets[name].set_sensors(sensors)

    def get_sensors(self, widget_name=None):
        if widget_name is None:
            widget_name = "main"

        sensors = self.sensor_widgets[widget_name].get_sensors()

        return sensors

    def update_ports(self):
        select = -1
        port_tag_tuples = et.utils.get_tagged_serial_ports()
        if os.name == "posix":
            ports = []
            for i, (port, tag) in enumerate(port_tag_tuples):
                tag_string = ""
                if tag:
                    select = i
                    tag_string = " ({})".format(tag)
                ports.append(port + tag_string)
        else:
            ports = [port for port, *_ in port_tag_tuples]

        self.ports_dd.clear()
        self.ports_dd.addItems(ports)
        if select >= 0:
            self.ports_dd.setCurrentIndex(select)

    def advanced_port(self):
        dialog = AdvancedSerialDialog(self.override_baudrate, self)
        ret = dialog.exec_()

        if ret == QtWidgets.QDialog.Accepted:
            self.override_baudrate = dialog.get_state()

        dialog.deleteLater()

    def start_btn_clicked(self):
        if self.get_gui_state("load_state") == LoadState.LOADED:
            self.data = None
            self.session_info_view.update(None)
            self.set_gui_state("load_state", LoadState.UNLOADED)
        else:
            self.start_scan()

    def save_file_btn_clicked(self):
        self.save_scan(self.data)

    def replay_btn_clicked(self):
        self.load_scan(restart=True)

    def save_rss_sensor_config_btn_clicked(self):
        stringToSave = _conf_to_rss_sdk.config_to_rss_usage(self, self.get_sensor_config())
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        title = "Save configuration"
        file_types = "Text file (*.txt)"
        filename, info = QtWidgets.QFileDialog.getSaveFileName(
            self, title, "", file_types, options=options
        )

        if filename:
            with open(filename, "w") as f:
                f.write(stringToSave)

    def init_buttons(self):
        # key: text, function, enabled, hidden, group
        button_info = {
            "save_rss_sensor_config": (
                "Save as C SDK config",
                self.save_rss_sensor_config_btn_clicked,
                True,
                False,
                "connection",
            ),
            "start": ("Start", self.start_btn_clicked, False, False, "scan"),
            "connect": ("Connect", self.connect_to_server, True, False, "connection"),
            "stop": ("Stop", self.stop_scan, False, False, "scan"),
            "load_scan": ("Load from file", self.load_scan, True, False, "scan"),
            "save_scan": ("Save to file", self.save_file_btn_clicked, False, False, "scan"),
            "replay_buffered": (
                "Replay",
                self.replay_btn_clicked,
                False,
                False,
                "scan",
            ),
            "scan_ports": ("Scan ports", self.update_ports, True, True, "connection"),
            "sensor_defaults": (
                "Defaults",
                self.sensor_defaults_handler,
                False,
                False,
                "sensor",
            ),
            "service_defaults": (
                "Defaults",
                self.service_defaults_handler,
                True,
                False,
                "service",
            ),
            "service_help": (
                "?",
                self.service_help_button_handler,
                True,
                False,
                "service",
            ),
            "advanced_defaults": (
                "Defaults",
                self.service_defaults_handler,
                True,
                False,
                "advanced",
            ),
            "save_process_data": (
                "Save process data",
                lambda: self.handle_advanced_process_data("save"),
                True,
                True,
                "advanced",
            ),
            "load_process_data": (
                "Load process data",
                lambda: self.handle_advanced_process_data("load"),
                True,
                True,
                "advanced",
            ),
            "advanced_port": (
                "Advanced port settings",
                self.advanced_port,
                True,
                True,
                "connection",
            ),
            "load_calibration": (
                "Load calibration",
                self.calibration_load_button_handler,
                True,
                False,
                "calibration",
            ),
            "save_calibration": (
                "Save calibration",
                self.calibration_save_button_handler,
                True,
                False,
                "calibration",
            ),
            "clear_calibration": (
                "Clear calibration",
                self.calibration_clear_button_handler,
                True,
                False,
                "calibration",
            ),
            "apply_calibration": (
                "Apply calibration",
                self.apply_current_calibration,
                True,
                False,
                "calibration",
            ),
        }

        self.buttons = {}
        for key, (text, fun, enabled, hidden, _) in button_info.items():
            btn = QPushButton(text, self)
            btn.clicked.connect(fun)
            btn.setEnabled(enabled)
            btn.setHidden(hidden)
            btn.setMinimumWidth(150)
            self.buttons[key] = btn

    def init_sublayouts(self):
        self.main_sublayout = QtWidgets.QGridLayout()
        self.main_sublayout.setContentsMargins(0, 3, 0, 3)
        self.main_sublayout.setSpacing(0)

        self.server_section = CollapsibleSection("Connection", is_top=True)
        self.main_sublayout.addWidget(self.server_section, 0, 0)

        # Interface. Always visible
        self.server_section.grid.addWidget(self.labels["interface"], 0, 0)
        self.server_section.grid.addWidget(self.interface_dd, 0, 1)

        # Protocol, always visible.
        self.server_section.grid.addWidget(self.labels["protocol"], 1, 0)
        self.server_section.grid.addWidget(self.protocol_dd, 1, 1)

        # Ports selection. Only visible with UART
        self.server_section.grid.addWidget(self.ports_dd, 2, 0)
        self.server_section.grid.addWidget(self.buttons["scan_ports"], 2, 1)

        # Host textfield. Only visible with Socket
        self.server_section.grid.addWidget(self.textboxes["host"], 3, 0, 1, 2)

        # Advanced port, visible with UART
        self.server_section.grid.addWidget(self.buttons["advanced_port"], 4, 0, 1, 2)

        self.server_section.grid.addWidget(self.buttons["connect"], 5, 0, 1, 2)
        self.server_section.grid.addWidget(self.labels["rssver"], 6, 0, 1, 2)

        self.control_section = CollapsibleSection("Scan controls")
        self.main_sublayout.addWidget(self.control_section, 1, 0)
        c = self.control_grid_count

        # Sublayout for service dropdown and a small help button.
        service_and_help_layout = QtWidgets.QHBoxLayout()
        service_and_help_layout.addWidget(self.module_dd)
        service_and_help_layout.addWidget(self.buttons["service_help"])
        self.buttons["service_help"].setFixedWidth(30)
        self.control_section.grid.addLayout(service_and_help_layout, c.pre_incr(), 0, 1, 2)

        self.control_section.grid.addWidget(self.labels["unsupported_mode"], c.pre_incr(), 0, 1, 2)
        self.control_section.grid.addWidget(self.buttons["start"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.buttons["stop"], c.val, 1)
        self.control_section.grid.addWidget(self.buttons["save_scan"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.buttons["load_scan"], c.val, 1)
        self.control_section.grid.addWidget(self.buttons["replay_buffered"], c.pre_incr(), 0, 1, 2)
        self.control_section.grid.addWidget(self.labels["data_source"], c.pre_incr(), 0, 1, 2)
        self.control_section.grid.addWidget(self.labels["sweep_buffer"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.textboxes["sweep_buffer"], c.val, 1)
        self.control_section.grid.addWidget(self.labels["stored_frames"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.textboxes["stored_frames"], c.val, 1)

        self.basic_sensor_config_section = CollapsibleSection("Sensor settings")
        self.main_sublayout.addWidget(self.basic_sensor_config_section, 4, 0)
        c = self.basic_sensor_param_count
        self.basic_sensor_config_section.grid.addWidget(
            self.buttons["sensor_defaults"], c.post_incr(), 0, 1, 2
        )

        self.basic_sensor_config_section.grid.addWidget(
            self.buttons["save_rss_sensor_config"], c.post_incr(), 0, 1, 2
        )

        self.basic_sensor_config_section.grid.addWidget(self.labels["sensor"], c.val, 0)

        sensor_selection = SensorSelection(error_handler=self.error_message)
        self.basic_sensor_config_section.grid.addWidget(sensor_selection, c.post_incr(), 1)
        self.sensor_widgets["main"] = sensor_selection

        self.advanced_sensor_config_section = CollapsibleSection(
            "Advanced sensor settings", init_collapsed=True
        )
        self.main_sublayout.addWidget(self.advanced_sensor_config_section, 5, 0)

        self.session_info_section = CollapsibleSection(
            "Session information (sensor metadata)", init_collapsed=True
        )
        self.main_sublayout.addWidget(self.session_info_section, 6, 0)
        self.session_info_view = SessionInfoView(self.session_info_section)
        self.session_info_section.grid.addWidget(self.session_info_view, 0, 0, 1, 2)

        self.basic_processing_config_section = CollapsibleSection("Processing settings")
        self.main_sublayout.addWidget(self.basic_processing_config_section, 7, 0)
        self.basic_processing_config_section.grid.addWidget(
            self.buttons["service_defaults"], 0, 0, 1, 2
        )

        self.advanced_processing_config_section = CollapsibleSection(
            "Advanced processing settings", init_collapsed=True
        )
        self.main_sublayout.addWidget(self.advanced_processing_config_section, 8, 0)
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["advanced_defaults"], 0, 0, 1, 2
        )
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["load_process_data"], 1, 0
        )
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["save_process_data"], 1, 1
        )

        self.calibration_config_section = CollapsibleSection(
            "Calibration management", init_collapsed=True
        )
        self.main_sublayout.addWidget(self.calibration_config_section, 9, 0)

        self.calibration_config_section.grid.addWidget(QLabel("Calibration source:"), 1, 0)
        self.calibration_config_section.grid.addWidget(self.textboxes["calibration_source"], 1, 1)

        self.calibration_config_section.grid.addWidget(QLabel("Calibration status:"), 2, 0)
        self.calibration_config_section.grid.addWidget(self.labels["calibration_status"], 2, 1)

        self.calibration_config_section.grid.addWidget(self.buttons["load_calibration"], 3, 0)
        self.calibration_config_section.grid.addWidget(self.buttons["save_calibration"], 3, 1)
        self.calibration_config_section.grid.addWidget(
            self.buttons["clear_calibration"], 4, 0, 1, 2
        )
        self.calibration_config_section.grid.addWidget(self.buttons["apply_calibration"], 5, 0)
        self.calibration_config_section.grid.addWidget(
            self.checkboxes["calibration_auto_apply"], 5, 1
        )

        self.main_sublayout.setRowStretch(12, 1)

    def init_panel_scroll_area(self):
        self.panel_scroll_area = QtWidgets.QScrollArea()
        self.panel_scroll_area.setFrameShape(QFrame.NoFrame)
        self.panel_scroll_area.setMinimumWidth(350)
        self.panel_scroll_area.setMaximumWidth(600)
        self.panel_scroll_area.setWidgetResizable(True)
        self.panel_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.panel_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.panel_scroll_area.horizontalScrollBar().setEnabled(False)

        self.panel_scroll_area_widget = QStackedWidget(self.panel_scroll_area)
        self.panel_scroll_area.setWidget(self.panel_scroll_area_widget)
        self.main_sublayout_widget = QWidget(self.panel_scroll_area_widget)
        self.main_sublayout_widget.setLayout(self.main_sublayout)
        self.panel_scroll_area_widget.addWidget(self.main_sublayout_widget)
        self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)

    def init_statusbar(self):
        self.statusBar().showMessage("Not connected")
        self.labels["sweep_info"].setFixedWidth(220)
        self.labels["sweep_info"].setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight)
        self.labels["measured_update_rate"].setToolTip("Measured update rate")
        self.labels["measured_update_rate"].setFixedWidth(120)
        self.statusBar().addPermanentWidget(self.labels["data_warnings"])
        self.statusBar().addPermanentWidget(self.labels["sweep_info"])
        self.statusBar().addPermanentWidget(self.labels["measured_update_rate"])
        self.statusBar().addPermanentWidget(self.labels["libver"])
        self.statusBar().addPermanentWidget(self.checkboxes["verbose"])
        self.statusBar().setStyleSheet("QStatusBar{border-top: 1px solid lightgrey;}")
        self.statusBar().show()

    def sensor_defaults_handler(self):
        config = self.get_sensor_config()

        if config is None:
            return

        default_config = self.current_module_info.sensor_config_class()
        config._loads(default_config._dumps())

    def service_defaults_handler(self):
        processing_config = self.get_processing_config()

        if processing_config is not None:
            processing_config._reset()

    def service_help_button_handler(self):
        if self.current_module_info and self.current_module_info.docs_url is None:
            return

        if self.current_module_info is None:
            url = (
                "https://acconeer-python-exploration.readthedocs.io/en/latest/services/index.html"
            )
        else:
            url = self.current_module_info.docs_url

        _ = webbrowser.open_new_tab(url)

    def _current_module_supports_calibration(self) -> bool:
        module_info = self.current_module_info
        return module_info is not None and (
            module_info.calibration_class is not None
            and module_info.calibration_mapper is not None
            and module_info.calibration_config_class is not None
        )

    def calibration_load_button_handler(self):
        """
        Loads a Calibration that was selected in a dialog window.
        The loaded Calibration is then assigned to applied to the current CalibrationConfiguration.
        """
        module_info = self.current_module_info

        if module_info is None:
            self.error_message("Load error", "Please select a module")
            return

        if not self._current_module_supports_calibration():
            self.error_message("Load error", "The selected module does not support calibration")
            return

        file_filter = ";;".join(
            desc for ext, desc in module_info.calibration_class.file_extensions()
        )

        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption="Load calibration",
            filter=file_filter,
            options=QtWidgets.QFileDialog.Options() | QtWidgets.QFileDialog.DontUseNativeDialog,
        )

        if not filename:
            self.error_message("No filename specified.")
            return

        loaded_calibration = module_info.calibration_class.load(path=filename)
        current_calibration_config = self.module_label_to_calibration_config_map[module_info.label]

        module_info.calibration_mapper.update_config_from_calibration(
            configuration=current_calibration_config,
            calibration=loaded_calibration,
        )

        self.calibration = loaded_calibration
        self.calibration_ui_state.load(filename)
        log.info(f"Loaded calibration from {filename}")
        self.refresh_pidgets()

    def calibration_save_button_handler(self):
        module_info = self.current_module_info
        if module_info is None:
            self.error_message("Save Error", "Please select a module")
            return

        if not self._current_module_supports_calibration():
            self.error_message("Save Error", "Selected module does not support calibration")
            return

        if self.calibration is None:
            self.error_message("Save Error", "No calibration is loaded.")
            return

        file_filter = ";;".join(
            desc for ext, desc in module_info.calibration_class.file_extensions()
        )
        exts = [ext for ext, desc in module_info.calibration_class.file_extensions()]

        filename, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption="Save calibration",
            filter=file_filter,
            options=QtWidgets.QFileDialog.Options() | QtWidgets.QFileDialog.DontUseNativeDialog,
        )

        if not filename:
            self.error_message("No filename specified.")
            return

        # if e.g. ".yaml" is not supplied in the save dialog, it won't save as ".yaml" either
        # This adds the first extension that is accepted by the `Calibration`.
        if not filename.endswith("." + exts[0]):
            filename += "." + exts[0]

        self.calibration.save(filename)
        self.calibration_ui_state.save(filename)

        log.info(f"Saved calibration as '{filename}'")

    def clear_application_owned_calibration(self):
        self.calibration_ui_state.clear()
        self.calibration = None

    def calibration_clear_button_handler(self):
        should_clear = not self.calibration_ui_state.modified or self.warning_message(
            "Are you sure you want to clear the calibration?", "Unsaved changes will be lost."
        )
        if not should_clear:
            return

        module_label = self.current_module_label
        calibration_config = self.module_label_to_calibration_config_map.get(module_label)

        if calibration_config:
            calibration_config._reset()

        self.clear_application_owned_calibration()

        processor = self.radar.external
        can_update_processors_calibration = (
            self.current_module_info is not None
            and isinstance(processor, self.current_module_info.processor)
            and hasattr(processor, "update_calibration")
        )
        if can_update_processors_calibration:
            processor.update_calibration(None)
            self.calibration_ui_state.calibration_status = CalibrationStatus.NONE

        self.refresh_pidgets()

    def set_calibration_auto_apply(self):
        cb_is_checked = self.checkboxes["calibration_auto_apply"].isChecked()
        self.calibration_ui_state.auto_apply = cb_is_checked

    def apply_current_calibration(self):
        if not self.calibration:
            self.error_message("Could not apply calibration as it is not present.")
            return

        if isinstance(self.radar.external, self.current_module_info.processor):
            self.radar.external.update_calibration(self.calibration)
            self.calibration_ui_state.calibration_status = CalibrationStatus.IN_PROCESSOR

    def update_canvas(self, force_update=False):
        module_label = self.module_dd.currentText()

        selectable_dd_labels = [SELECT_A_SERVICE_TEXT]
        selectable_dd_labels.extend(MODULE_LABEL_TO_MODULE_INFO_MAP.keys())
        while (
            module_label not in selectable_dd_labels
        ):  # Fixes bug when using arrow keys to go trough dropdown
            direction = self.module_dd.findText(module_label) - self.module_dd.findText(
                self.current_module_label or SELECT_A_SERVICE_TEXT
            )

            if direction < 0:
                index = self.module_dd.findText(module_label) - 2
                # Seperator has an index
            else:
                index = self.module_dd.findText(module_label) + 1

            self.module_dd.blockSignals(True)
            self.module_dd.setCurrentIndex(index)
            self.module_dd.blockSignals(False)

            module_label = self.module_dd.currentText()

        switching_module = self.current_module_label != module_label
        self.current_module_label = module_label

        self.current_module_info = MODULE_LABEL_TO_MODULE_INFO_MAP.get(module_label, None)

        if self.current_module_info is None:
            data_type = None
            self.external = None
        else:
            data_type = self.current_module_info.sensor_config_class().mode
            self.external = self.current_module_info.processor

        switching_data_type = self.current_data_type != data_type
        self.current_data_type = data_type

        if switching_data_type:
            self.data = None
            self.session_info_view.update(None)
            self.set_gui_state("load_state", LoadState.UNLOADED)

        if force_update or switching_module:
            if not switching_module:
                self.get_processing_config()

            new_canvas = self.init_graphs()
            self.swap_canvas(new_canvas)

    def swap_canvas(self, new_canvas):
        if self.canvas is not None:
            self.canvas_layout.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()

        self.canvas_layout.addWidget(new_canvas)
        self.canvas = new_canvas

    def populate_protocol_dd(self, *text_data_tuples: Tuple[str, Any]):
        """
        Populates the Protocol dropdown (self.protocol_dd)

        :param text_data_tuples:
            Variable number of tuples of (<displayed text>, <data>).
            The first one passed will be the default (as it will have index=0)
            If only one tuples is passed, the dropdown will be disabled as no choice can be made.
        """
        self.protocol_dd.setEnabled(len(text_data_tuples) > 1)
        for text, data in text_data_tuples:
            self.protocol_dd.addItem(text, userData=data)

    def update_interface(self):
        EXPLORATION_DD_ITEM = ("Exploration", et.a111.Protocol.EXPLORATION)
        AUTODETECT_DD_ITEM = ("Auto-detected", None)
        MODULE_DD_ITEM = ("Module", et.a111.Protocol.MODULE)
        NA_DD_ITEM = ("Not Applicable", None)

        if self.gui_states["server_connected"]:
            self.connect_to_server()
        link = self.interface_dd.currentData()

        # Start from clean slate
        self.ports_dd.hide()
        self.buttons["advanced_port"].hide()
        self.buttons["scan_ports"].hide()
        self.textboxes["host"].hide()
        self.protocol_dd.clear()

        if link == et.a111.Link.UART:
            self.ports_dd.show()
            self.buttons["advanced_port"].show()
            self.buttons["scan_ports"].show()
            self.update_ports()
            self.populate_protocol_dd(MODULE_DD_ITEM, EXPLORATION_DD_ITEM)
        elif link == et.a111.Link.SPI:
            self.populate_protocol_dd(MODULE_DD_ITEM)
        elif link == et.a111.Link.SOCKET:
            self.textboxes["host"].show()
            self.populate_protocol_dd(AUTODETECT_DD_ITEM)
        elif link == "mock":
            self.populate_protocol_dd(NA_DD_ITEM)

        self.set_multi_sensors()

    def error_message(self, text, info_text=None):
        if self.under_test:
            raise Exception

        if not text:
            return

        message_box = BiggerMessageBox(self.main_widget)
        message_box.setIcon(QtWidgets.QMessageBox.Warning)
        message_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        message_box.setWindowTitle("Alert")

        message_box.setText(text.replace("\n", "<br>"))
        if info_text:
            message_box.setInformativeText(info_text.replace("\n", "<br>"))
        if any(sys.exc_info()):
            detailed_text = traceback.format_exc()
            message_box.setDetailedText(detailed_text)

        message_box.exec_()

    def info_handle(self, info, detailed_info=None, blocking=True):
        msg = QtWidgets.QMessageBox(self.main_widget)
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setText(info)
        if detailed_info:
            msg.setDetailedText(detailed_info)
        msg.setWindowTitle("Info")
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        if blocking:
            msg.exec_()
        else:
            msg.show()
        return msg

    def warning_message(self, warning, detailed_warning=None):
        msg = QtWidgets.QMessageBox(self.main_widget)
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setText(warning)
        if detailed_warning:
            msg.setDetailedText(detailed_warning)
        msg.setWindowTitle("Warning")
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel)
        retval = msg.exec_()
        return retval == 1024

    def start_scan(self, from_file=False):
        self.sig_scan.emit("start", "", None)
        if not self.get_sensors():
            self.error_message("Please select at least one sensor")
            return

        if self.current_module_info is None:
            self.error_message("Please select a service or detector")
            return

        try:
            sweep_buffer = int(self.textboxes["sweep_buffer"].text())
            assert sweep_buffer > 0
        except (ValueError, AssertionError):
            self.textboxes["sweep_buffer"].setText(str("1000"))
            self.error_message("Sweep buffer needs to be a positive integer")
            return

        sensor_config = self.get_sensor_config()

        if from_file:
            sensor_config._loads(self.data.sensor_config_dump)
            self.set_gui_state("replaying_data", True)

        self.update_canvas(force_update=True)

        processing_config = self.get_processing_config()
        sensor_config = self.save_gui_settings_to_sensor_config()
        calibration_config = self.get_calibration_config()

        params = {
            "sensor_config": sensor_config,
            "data_source": "file" if from_file else "stream",
            "module_info": self.current_module_info,
            "sweep_buffer": sweep_buffer,
            "service_params": processing_config,
            "multi_sensor": self.current_module_info.multi_sensor,
            "rss_version": getattr(self, "rss_version", None),
            "calibration": self.calibration,
        }

        self.threaded_scan = Threaded_Scan(params, parent=self)
        self.threaded_scan.sig_scan.connect(self.thread_receive)
        self.sig_scan.connect(self.threaded_scan.receive)

        self.module_dd.setEnabled(False)

        self.num_recv_frames = 0
        self.num_missed_frames = 0
        self.measured_update_rate_fc.reset()
        self.reset_missed_frame_text_time = None
        self.threaded_scan.start()

        if processing_config is not None:
            self.basic_processing_config_section.body_widget.setEnabled(True)
            self.buttons["service_defaults"].setEnabled(False)
            self.buttons["advanced_defaults"].setEnabled(False)
            processing_config._state = et.configbase.Config.State.LIVE
        else:
            self.basic_processing_config_section.body_widget.setEnabled(False)

        if calibration_config:
            calibration_config._state = et.configbase.Config.State.LOADED_READONLY

        self.buttons["connect"].setEnabled(False)

        self.set_gui_state("scan_is_running", True)

    def set_gui_state(self, state, val):
        if state in self.gui_states:
            self.gui_states[state] = val
        elif state is None:
            pass
        else:
            print("{} is an unknown state!".format(state))
            return

        states = self.gui_states

        # Visible, enabled, text

        # Start button
        self.buttons["start"].setEnabled(
            all(
                [
                    self.in_supported_mode or states["load_state"] == LoadState.LOADED,
                    not states["scan_is_running"],
                    not states["has_config_error"],
                    states["server_connected"] or states["load_state"] == LoadState.LOADED,
                ]
            )
        )
        if states["load_state"] == LoadState.LOADED:
            self.buttons["start"].setText("New measurement")
        else:
            self.buttons["start"].setText("Start measurement")

        # Stop button
        self.buttons["stop"].setEnabled(states["scan_is_running"])

        # Save to file button
        self.buttons["save_scan"].setEnabled(
            all(
                [
                    states["load_state"] != LoadState.UNLOADED,
                    not states["scan_is_running"],
                ]
            )
        )

        # Load from file button
        self.buttons["load_scan"].setEnabled(not states["scan_is_running"])

        # Replay button
        self.buttons["replay_buffered"].setEnabled(
            all(
                [
                    states["load_state"] != LoadState.UNLOADED,
                    not states["scan_is_running"],
                ]
            )
        )

        # Data source
        self.labels["data_source"].setVisible(
            bool(states["load_state"] == LoadState.LOADED and self.data_source)
        )
        try:
            text = "Loaded " + os.path.basename(self.data_source)
        except Exception:
            text = ""
        if len(text) > 50:
            text = text[:47] + "..."
        self.labels["data_source"].setText(text)

        # Sweep buffer
        self.labels["sweep_buffer"].setVisible(states["load_state"] != LoadState.LOADED)
        self.textboxes["sweep_buffer"].setVisible(states["load_state"] != LoadState.LOADED)
        self.textboxes["sweep_buffer"].setEnabled(not states["scan_is_running"])

        # Stored frames
        if states["load_state"] == LoadState.LOADED:
            text = "Number of frames"
        else:
            text = "Buffered frames"
        self.labels["stored_frames"].setText(text)
        try:
            num_stored = len(self.data.data)
        except Exception:
            num_stored = 0
        self.textboxes["stored_frames"].setText(str(num_stored))

        # RSS version
        lbl = self.labels["rssver"]

        try:
            strict_ver = states["connection_info"]["strict_version"]
        except Exception:
            strict_ver = None

        if strict_ver is not None:
            if strict_ver < version.parse(et.a111.SDK_VERSION):
                ver_mismatch = "RSS server"
            elif strict_ver > version.parse(et.a111.SDK_VERSION):
                ver_mismatch = "Exploration Tool"
            else:
                ver_mismatch = None

            text = "RSS v" + str(strict_ver)

            if ver_mismatch:
                text += " ({} upgrade recommended)".format(ver_mismatch)
                lbl.setStyleSheet("QLabel {color: red}")
            else:
                lbl.setStyleSheet("")

            lbl.setText(text)
            lbl.show()
        else:
            lbl.hide()

        # Unsupported mode warning
        visible = self.in_supported_mode is not None and not self.in_supported_mode
        self.labels["unsupported_mode"].setVisible(visible)

        # Other

        sensor_config = self.get_sensor_config()
        if sensor_config:
            if states["load_state"] == LoadState.LOADED:
                sensor_config._state = et.configbase.Config.State.LOADED_READONLY
            elif not states["scan_is_running"]:
                sensor_config._state = et.configbase.Config.State.LOADED
            else:
                sensor_config._state = et.configbase.Config.State.LIVE

        calibration_config = self.get_calibration_config()
        if calibration_config:
            if self.calibration is None:
                # Covers case where scan is stopped before a calibration
                # is returned from the processor, which would leave the config
                # in an editable state.
                calibration_config._state = et.configbase.Config.State.LOADED_READONLY
            else:
                if states["load_state"] == LoadState.LOADED:
                    calibration_config._state = et.configbase.Config.State.LOADED_READONLY
                elif not states["scan_is_running"]:
                    calibration_config._state = et.configbase.Config.State.LOADED
                else:
                    calibration_config._state = et.configbase.Config.State.LIVE

        for sensor_widget in self.sensor_widgets.values():
            sensor_widget.setEnabled(not states["scan_is_running"])

        self.set_multi_sensors()
        self.calibration_ui_state.scan_is_running = states["scan_is_running"]

        self.buttons["sensor_defaults"].setEnabled(not states["scan_is_running"])

        if state == "server_connected":
            connected = val
            if connected:
                self.buttons["connect"].setText("Disconnect")
                self.buttons["connect"].setStyleSheet("QPushButton {color: red}")
                self.buttons["advanced_port"].setEnabled(False)
                self.set_multi_sensors()
            else:
                self.buttons["connect"].setText("Connect")
                self.buttons["connect"].setStyleSheet("QPushButton {color: black}")
                self.buttons["advanced_port"].setEnabled(True)
                self.statusBar().showMessage("Not connected")

        if self.current_module_info is None:
            tooltip_text = "Get help with services on the Acconeer documentation pages"
        elif self.current_module_info.docs_url is not None:
            tooltip_text = (
                f'Get help with "{self.current_module_info.label}" '
                + "on the Acconeer documentation pages"
            )
        else:
            tooltip_text = None

        help_button_disabled = (
            self.current_module_info and self.current_module_info.docs_url is None
        )
        self.buttons["service_help"].setEnabled(not help_button_disabled)
        self.buttons["service_help"].setToolTip(tooltip_text)

    def get_gui_state(self, state):
        if state in self.gui_states:
            return self.gui_states[state]
        else:
            print("{} is an unknown state!".format(state))
            return

    def stop_scan(self):
        self.sig_scan.emit("stop", "", None)

    def unlock_gui(self):
        self.module_dd.setEnabled(True)
        self.buttons["connect"].setEnabled(True)
        self.basic_processing_config_section.body_widget.setEnabled(True)

        processing_config = self.get_processing_config()
        if processing_config is not None:
            self.buttons["service_defaults"].setEnabled(True)
            self.buttons["advanced_defaults"].setEnabled(True)
            processing_config._state = et.configbase.Config.State.LOADED

        self.set_gui_state("replaying_data", False)

        self.set_gui_state("scan_is_running", False)

    def set_log_level(self):
        log_level = logging.INFO
        if self.checkboxes["verbose"].isChecked():
            log_level = logging.DEBUG
        et.utils.set_loglevel(log_level)

    def get_client_arguments_from_ui_elements(self):
        link = self.interface_dd.currentData()
        protocol = self.protocol_dd.currentData()

        if link == "mock":
            return dict(mock=True)

        kwargs = dict(link=link, protocol=protocol)

        if link == et.a111.Link.SOCKET:
            kwargs["host"] = self.textboxes["host"].text()
        elif link == et.a111.Link.UART:
            port_label = self.ports_dd.currentText()
            port, *_ = port_label.split(" ")
            kwargs["serial_port"] = port

        if self.override_baudrate is not None:
            kwargs["override_baudrate"] = self.override_baudrate

        return kwargs

    def connect_to_server(self):
        if not self.get_gui_state("server_connected"):
            client_kwargs = self.get_client_arguments_from_ui_elements()
            self.client = et.a111.Client(**client_kwargs)

            statusbar_connection_info = self.client.description

            if self.override_baudrate:
                log.warning(f"Overriding baudrate ({self.override_baudrate})!")

            self.client.squeeze = False

            try:
                info = self.client.connect()
            except Exception:
                text = "Could not connect to server"
                info_text = None

                if self.client.get_link_type() == et.a111.Link.UART:
                    info_text = (
                        "Did you select the right COM port?"
                        " Try unplugging and plugging back in the module!"
                    )

                self.error_message(text, info_text=info_text)
                return

            self.rss_version = info.get("version_str", None)

            connected_sensors = [1]  # for the initial set
            self.sensors_available = [1]  # for the sensor widget(s)

            if self.client.get_link_type() == et.a111.Link.SOCKET:
                sensor_count = min(info.get("board_sensor_count", 4), 4)
                self.sensors_available = list(range(1, sensor_count + 1))

                if sensor_count > 1:
                    config = et.a111.SparseServiceConfig()
                    connected_sensors = []
                    for i in range(sensor_count):
                        sensor = i + 1
                        config.sensor = sensor
                        try:
                            self.client.start_session(config)
                            self.client.stop_session()
                        except et.a111.SessionSetupError:
                            pass
                        except Exception:
                            self.error_message("Could not connect to server")
                            return
                        else:
                            connected_sensors.append(sensor)
            if self.client.get_link_type() == "mock":
                self.sensors_available = list(range(1, 5))

            if not connected_sensors:
                self.error_message("No sensors connected, check connections")
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                return

            self.set_sensors(connected_sensors)
            self.set_gui_state("server_connected", True)
            self.set_gui_state("load_state", LoadState.UNLOADED)
            self.set_gui_state("connection_info", info)
            self.statusBar().showMessage("Connected via {}".format(statusbar_connection_info))
            if self.current_module_info is None:
                self.module_dd.setCurrentIndex(1)
        else:
            self.sensors_available = None
            self.set_gui_state("server_connected", False)
            self.set_gui_state("connection_info", None)
            self.sig_scan.emit("stop", "", None)
            try:
                self.client.stop_session()
            except Exception:
                pass

            try:
                self.client.disconnect()
            except Exception:
                pass

    def load_gui_settings_from_sensor_config(self, config=None):  # TODO
        return

    def save_gui_settings_to_sensor_config(self):  # TODO
        return self.get_sensor_config()

    def is_float(self, val, is_positive=True):
        try:
            f = float(val)
            if is_positive and f <= 0:
                raise ValueError("Not positive")
            return f
        except Exception:
            return False

    def check_limit(self, val, field, start, end, set_to=None):
        out_of_range = False
        try:
            float(val)
        except (ValueError, TypeError):
            val = start
            out_of_range = True
        if val < start:
            val = start
            out_of_range = True
        if val > end:
            val = end
            out_of_range = True
        if out_of_range:
            if set_to is not None:
                val = set_to
            field.setText(str(val))
        return val, out_of_range

    def load_scan(self, restart=False):
        if restart:
            self.set_gui_state("load_state", LoadState.LOADED)
            self.start_scan(from_file=True)
            return

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load scan",
            "",
            "HDF5 data files (*.h5);; NumPy data files (*.npz)",
            options=options,
        )

        if not filename:
            return

        try:
            record = et.a111.recording.load(filename)
        except Exception:
            traceback.print_exc()
            self.error_message(
                (
                    "Failed to load file"
                    "\n\n"
                    "Note: loading data fetched with RSS v1 is not supported."
                    "To load old data, please use an older version of the Exploration Tool."
                )
            )
            return

        try:
            if record.module_key is None:
                raise Exception

            module_info = MODULE_KEY_TO_MODULE_INFO_MAP[record.module_key]
            index = self.module_dd.findText(module_info.label, QtCore.Qt.MatchFixedString)
        except Exception:
            has_loaded_module = False
            print("Can't find the module for the loaded data")
        else:
            has_loaded_module = index != -1

        if not has_loaded_module:  # Just try loading the data in the service-only module
            try:
                module_info = MODULE_KEY_TO_MODULE_INFO_MAP[record.mode.name.lower()]
                index = self.module_dd.findText(module_info.label, QtCore.Qt.MatchFixedString)
            except Exception:
                self.error_message("Unknown mode in loaded file")
                return

        self.module_dd.setCurrentIndex(index)
        self.update_canvas()

        self.data = record

        sensor_config = self.get_sensor_config()
        sensor_config._loads(record.sensor_config_dump)

        # Order is important for the following 3 calls
        self.set_multi_sensors()
        self.set_sensors(sensor_config.sensor)
        self.set_gui_state("load_state", LoadState.LOADED)

        if has_loaded_module:
            processing_config = self.get_processing_config()
            if isinstance(processing_config, et.configbase.ProcessingConfig):
                if record.processing_config_dump is not None:
                    try:
                        processing_config._loads(record.processing_config_dump)
                    except Exception:
                        traceback.print_exc()
            else:
                try:
                    self.load_legacy_processing_config_dump(record)
                except Exception:
                    traceback.print_exc()

        self.data_source = filename
        self.start_scan(from_file=True)

    def save_scan(self, record):
        if len(record.data) == 0:
            self.error_message("No data to save")
            return

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        title = "Save scan"
        file_types = "HDF5 data files (*.h5);; NumPy data files (*.npz)"
        filename, info = QtWidgets.QFileDialog.getSaveFileName(
            self, title, "", file_types, options=options
        )

        if not filename:
            return

        record.mode = self.get_sensor_config().mode
        record.module_key = self.current_module_info.key

        record.processing_config_dump = None
        record.legacy_processing_config_dump = None

        processing_config = self.get_processing_config()
        if processing_config is not None:
            record.processing_config_dump = processing_config._dumps()

        try:
            if "h5" in info:
                et.a111.recording.save_h5(filename, record)
            else:
                et.a111.recording.save_npz(filename, record)
        except Exception as e:
            traceback.print_exc()
            self.error_message("Failed to save file:\n {:s}".format(e))

    def thread_receive(self, message_type, message, data=None):
        if "error" in message_type:
            if message_type == "session_setup_error":
                error = "Failed to setup session (bad config)!\n"
                if "socket" in self.interface_dd.currentText().lower():
                    error += "Check that selected sensors are connected and working!\n"
                    error += "Check Streaming server log for erros!"
                self.error_message(error)
            elif "client" in message_type:
                self.stop_scan()
                if self.get_gui_state("server_connected"):
                    self.connect_to_server()
            elif "proccessing" in message_type:
                self.stop_scan()
            self.error_message("{}".format(message))
        elif message_type == "scan_data":
            if self.get_gui_state("load_state") != LoadState.LOADED:
                self.data = data
                self.data_source = None
                self.set_gui_state("load_state", LoadState.BUFFERED)
        elif message_type == "scan_done":
            self.unlock_gui()
        elif "update_external_plots" in message_type:
            if data is not None:
                self.update_external_plots(data)
        elif "sweep_info" in message_type:
            self.update_sweep_info(data)
        elif "session_info" in message_type:
            self.session_info = data
            self.reload_pg_updater(session_info=data)
            self.session_info_view.update(self.session_info)
        elif "process_data" in message_type:
            self.advanced_process_data["process_data"] = data
        elif "set_sensors" in message_type:
            self.set_sensors(data)
        elif "new_calibration" in message_type:
            should_update_calibration = (
                self.current_module_info
                and self.current_module_info.calibration_mapper is not None
            )
            if should_update_calibration:
                self.calibration = data
                calibration_config = self.module_label_to_calibration_config_map[
                    self.current_module_label
                ]
                self.current_module_info.calibration_mapper.update_config_from_calibration(
                    configuration=calibration_config,
                    calibration=self.calibration,
                )
                self.calibration_ui_state.buffer("Session")

                if self.calibration_ui_state.auto_apply:
                    self.apply_current_calibration()

                self.refresh_calibration_pidgets()
        else:
            print("Thread data not implemented!")
            print(message_type, message, data)

    def update_external_plots(self, data):
        self.plot_queue.append(data)

    def plot_timer_fun(self):
        if not self.plot_queue:
            return

        data, *self.plot_queue = self.plot_queue[-2:]
        self.service_widget.update(data)

    def update_sweep_info(self, infos):
        if not isinstance(infos, list):  # If squeezed
            infos = [infos]

        missed = any([e.get("missed_data", False) for e in infos])
        saturated = any([e.get("data_saturated", False) for e in infos])
        data_quality_warning = any([e.get("data_quality_warning", False) for e in infos])

        if missed:
            self.num_missed_frames += 1

        self.num_recv_frames += 1

        show_lim = int(1e6)
        num_missed_show = min(self.num_missed_frames, show_lim)
        missed_sym = ">" if num_missed_show >= show_lim else ""
        num_recv_show = min(self.num_recv_frames, show_lim)
        recv_sym = ">" if num_recv_show >= show_lim else ""

        text = "Frames: {:s}{:d} (missed {:s}{:d})".format(
            recv_sym,
            num_recv_show,
            missed_sym,
            num_missed_show,
        )
        self.labels["sweep_info"].setText(text)

        tick_info = self.measured_update_rate_fc.tick_values()
        if tick_info is not None:
            _, f, _ = tick_info

            self.labels["measured_update_rate"].setText(f"{f:>10.1f} Hz")

        RED_TEXT_TIMEOUT = 2
        now = time.time()

        if missed:
            self.labels["sweep_info"].setStyleSheet("QLabel {color: red}")
            self.reset_missed_frame_text_time = now + RED_TEXT_TIMEOUT
        if self.reset_missed_frame_text_time is None or self.reset_missed_frame_text_time < now:
            self.labels["sweep_info"].setStyleSheet("")

        if data_quality_warning:
            self.labels["data_warnings"].setText("Warning: Bad data quality, restart service!")
        elif saturated:
            self.labels["data_warnings"].setText("Warning: Data saturated, reduce gain!")

        self.labels["data_warnings"].setVisible(saturated or data_quality_warning)

        if self.get_gui_state("load_state") != LoadState.LOADED:
            try:
                text = str(min(self.num_recv_frames, int(self.textboxes["sweep_buffer"].text())))
            except Exception:
                text = ""
            self.textboxes["stored_frames"].setText(text)

    def start_up(self):
        if self.under_test:
            return

        if self.use_last_config and os.path.isfile(LAST_CONF_FILENAME):
            try:
                last = np.load(LAST_CONF_FILENAME, allow_pickle=True)
                self.load_last_config(last.item())
                log.info(f"Loaded configuration from last session: {LAST_CONF_FILENAME}")
            except Exception as e:
                print("Could not load settings from last session\n{}".format(e))

    def load_last_config(self, last_config):
        # Restore sensor configs (configbase)
        dumps = last_config.get("sensor_config_dumps", {})
        for key, conf in self.module_label_to_sensor_config_map.items():
            if key in dumps:
                dump = last_config["sensor_config_dumps"][key]
                try:
                    conf._loads(dump)
                except Exception:
                    print("Could not load sensor config for '{}'".format(key))
                    conf._reset()  # TODO: load module defaults

        # Restore processing configs (configbase)
        dumps = last_config.get("processing_config_dumps", {})
        for key, conf in self.module_label_to_processing_config_map.items():
            if key in dumps:
                dump = last_config["processing_config_dumps"][key]
                try:
                    conf._loads(dump)
                except Exception:
                    print("Could not load processing config for '{}'".format(key))
                    conf._reset()

        # Restore misc. settings
        self.textboxes["sweep_buffer"].setText(last_config["sweep_buffer"])
        self.ports_dd.setCurrentIndex(last_config["port"])
        self.textboxes["host"].setText(last_config["host"])

        interface_index = last_config["interface"]
        if interface_index not in range(0, self.interface_dd.count()):
            interface_index = 0
        self.interface_dd.setCurrentIndex(interface_index)

        if last_config.get("override_baudrate"):
            self.override_baudrate = last_config["override_baudrate"]

    def closeEvent(self, event=None):
        sensor_config_dumps = {}
        for module_label, config in self.module_label_to_sensor_config_map.items():
            try:
                sensor_config_dumps[module_label] = config._dumps()
            except AttributeError:
                pass

        processing_config_dumps = {}
        for module_label, config in self.module_label_to_processing_config_map.items():
            try:
                processing_config_dumps[module_label] = config._dumps()
            except AttributeError:
                pass

        last_config = {
            "sensor_config_dumps": sensor_config_dumps,
            "processing_config_dumps": processing_config_dumps,
            "host": self.textboxes["host"].text(),
            "sweep_buffer": self.textboxes["sweep_buffer"].text(),
            "interface": self.interface_dd.currentIndex(),
            "port": self.ports_dd.currentIndex(),
            "override_baudrate": self.override_baudrate,
        }

        if self.use_last_config and not self.under_test:
            np.save(LAST_CONF_FILENAME, last_config, allow_pickle=True)
            log.info(f"Saved configuration from this session to {LAST_CONF_FILENAME}")

        try:
            self.client.disconnect()
        except Exception:
            pass

        self.close()

    def get_sensor_config(self):
        module_info = self.current_module_info

        if module_info is None:
            return None

        module_label = module_info.label
        config = self.module_label_to_sensor_config_map[module_label]

        if len(self.get_sensors()):
            config.sensor = self.get_sensors()
        else:
            config.sensor = [1]
            self.set_sensors([1])

        return config

    def get_processing_config(self, module_label=None):
        if module_label is None:
            module_info = self.current_module_info
        else:
            module_info = MODULE_LABEL_TO_MODULE_INFO_MAP[module_label]

        if module_info is None:
            return None

        module_label = module_info.label
        return self.module_label_to_processing_config_map[module_label]

    def get_default_processing_config(self, module_label=None):
        if module_label is not None:
            module_info = MODULE_LABEL_TO_MODULE_INFO_MAP[module_label]
        else:
            module_info = self.current_module_info

        if module_info is None:
            return {}

        if module_info.processing_config_class is None:
            return {}

        return module_info.processing_config_class()

    def get_calibration_config(self):
        module_info = self.current_module_info

        if module_info is None:
            return None

        return self.module_label_to_calibration_config_map.get(module_info.label)

    @property
    def in_supported_mode(self):
        try:
            return self.get_sensor_config().mode in self.client.supported_modes
        except (AttributeError, TypeError):
            return None


class Threaded_Scan(QtCore.QThread):
    sig_scan = Signal(str, str, object)

    def __init__(self, params, parent=None):
        QtCore.QThread.__init__(self, parent)

        self.client = parent.client
        self.radar = parent.radar
        self.sensor_config = params["sensor_config"]
        self.params = params
        self.data = parent.data
        self.parent = parent
        self.running = True

        self.finished.connect(self.stop_thread)

    def stop_thread(self):
        self.quit()

    def run(self):
        if self.params["data_source"] == "stream":
            record = None

            try:
                session_info = self.client.setup_session(self.sensor_config)
                self._emit("session_info", "", session_info)
                self.radar.prepare_processing(self, self.params, session_info)
                self.client.start_session()
            except et.a111.SessionSetupError:
                self.running = False
                self._emit("session_setup_error", "")
            except Exception as e:
                traceback.print_exc()
                self._emit(
                    "client_error",
                    "Failed to setup streaming!\n" "{}".format(self.format_error(e)),
                )
                self.running = False

            try:
                while self.running:
                    info, sweep = self.client.get_next()
                    self._emit("sweep_info", "", info)
                    process_results, record = self.radar.process(sweep, info)

                    if isinstance(process_results, dict) and "new_calibration" in process_results:
                        self._emit("new_calibration", "", process_results["new_calibration"])
            except Exception as e:
                traceback.print_exc()
                msg = "Failed to communicate with server!\n{}".format(self.format_error(e))
                self._emit("client_error", msg)

            try:
                self.client.stop_session()
            except Exception:
                pass

            if record is not None and len(record.data) > 0:
                self._emit("scan_data", "", record)
        elif self.params["data_source"] == "file":
            self._emit("session_info", "ok", self.data.session_info)

            try:
                self.radar.prepare_processing(self, self.params, self.data.session_info)
                self.radar.process_saved_data(self.data, self)
            except Exception as e:
                traceback.print_exc()
                error = self.format_error(e)
                self._emit("processing_error", "Error while replaying data:<br>" + error)
        else:
            self._emit("error", "Unknown mode %s!" % self.mode)
        self._emit("scan_done", "", "")

    def receive(self, message_type, message, data=None):
        if message_type == "stop":
            if self.running:
                self.running = False
                self.radar.abort_processing()
        elif message_type == "update_feature_extraction":
            self.radar.update_feature_extraction(message, data)
        elif message_type == "update_feature_list":
            self.radar.update_feature_list(data)
        elif message_type == "start":
            pass
        else:
            print("Scan thread received unknown signal: {}".format(message_type))

    def _emit(self, message_type, message, data=None):
        self.sig_scan.emit(message_type, message, data)

    def format_error(self, e):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err = "{}\n{}\n{}\n{}".format(exc_type, fname, exc_tb.tb_lineno, e)
        return err


def sigint_handler(gui):
    event = threading.Event()
    thread = threading.Thread(target=watchdog, args=(event,))
    thread.start()
    gui.closeEvent()
    event.set()
    thread.join()


def watchdog(event):
    flag = event.wait(1)
    if not flag:
        print("\nforcing exit...")
        os._exit(1)


def remove_user_data_files():
    """Removes all files under USER_DATA_DIR interactively"""
    user_data_dir = pathlib.Path(USER_DATA_DIR)
    if not user_data_dir.exists():
        print(f'Config folder ("{user_data_dir}") does not exists.')
        print("Nothing will be done.")
        return

    if not any(user_data_dir.iterdir()):
        print(f'There exists no files under "{user_data_dir}".')
        print("Nothing will be done.")
        return

    print("Proceeding will remove the following files:\n")
    for file in user_data_dir.iterdir():
        print(f"    * {file}")
    print()

    choice = input("Continue? [y/N] ")
    should_remove = choice.lower().startswith("y")
    if should_remove:
        for file in user_data_dir.iterdir():
            file.unlink()  # unlink <=> rm
            print(f'Removed "{file}"')
    else:
        print("Nothing was removed.")


def main():
    et.utils.config_logging(level=logging.INFO)

    # Enable warnings to be printed to the log, e.g. DeprecationWarning
    warnings.simplefilter("module")

    args = ExptoolArgumentParser().parse_args()

    if args.purge_config:
        remove_user_data_files()
        sys.exit(0)

    if args.use_last_config:
        if not os.path.exists(USER_DATA_DIR):
            log.info(f"Creating folder {USER_DATA_DIR}")

        os.makedirs(USER_DATA_DIR, exist_ok=True)

    if args.portable:
        pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    ex = GUI(use_last_config=args.use_last_config)

    signal.signal(signal.SIGINT, lambda *_: sigint_handler(ex))

    # Makes sure the signal is caught
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)

    sys.exit(app.exec())
