import copy
import json
import logging
import os
import re
import signal
import sys
import threading
import traceback

import numpy as np
import pyqtgraph as pg
import serial.tools.list_ports

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QWidget,
)


HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.append(HERE)
sys.path.append(os.path.abspath(os.path.join(HERE, "..")))
sys.path.append(os.path.abspath(os.path.join(HERE, "ml")))
sys.path.append(os.path.abspath(os.path.join(HERE, "elements")))


try:
    from acconeer.exptool import clients, recording, utils
    from acconeer.exptool.structs import configbase

    import data_processing
    from helper import (
        AdvancedSerialDialog,
        CollapsibleSection,
        Count,
        GUIArgumentParser,
        Label,
        SensorSelection,
        lib_version_up_to_date,
    )
    from modules import (
        MODULE_INFOS,
        MODULE_LABEL_TO_MODULE_INFO_MAP,
        MODULE_KEY_TO_MODULE_INFO_MAP,
    )
except Exception:
    traceback.print_exc()
    print("\nPlease update your library with 'python -m pip install -U --user .'")
    sys.exit(1)


if "win32" in sys.platform.lower():
    import ctypes
    myappid = "acconeer.exploration.tool"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


class GUI(QMainWindow):
    DEFAULT_BAUDRATE = 3000000
    ACC_IMG_FILENAME = os.path.join(HERE, "elements/acc.png")
    LAST_CONF_FILENAME = os.path.join(HERE, "last_config.npy")
    LAST_ML_CONF_FILENAME = os.path.join(HERE, "last_ml_config.npy")

    sig_scan = pyqtSignal(str, str, object)
    sig_sensor_config_pidget_event = pyqtSignal(object)
    sig_processing_config_pidget_event = pyqtSignal(object)

    def __init__(self, under_test=False):
        super().__init__()

        self.under_test = under_test

        self.data = None
        self.client = None
        self.sweep_buffer = 500
        self.num_recv_frames = 0
        self.num_missed_frames = 0
        self.service_labels = {}
        self.service_params = None
        self.service_defaults = None
        self.advanced_process_data = {"use_data": False, "process_data": None}
        self.override_baudrate = None
        self.session_info = None
        self.threaded_scan = None

        self.gui_states = {
            "has_loaded_data": False,
            "server_connected": False,
            "replaying_data": False,
            "ml_plotting_extraction": False,
            "ml_plotting_evaluation": False,
            "ml_mode": False,
            "ml_tab": "main",
            "scan_is_running": False,
        }

        self.current_data_type = None
        self.current_module_label = None
        self.canvas = None
        self.multi_sensor_interface = True
        self.basic_sensor_param_count = Count()
        self.advanced_sensor_param_count = Count()
        self.control_grid_count = Count()
        self.param_grid_count = Count(2)
        self.sensor_widgets = {}

        self.ml_feature_plot_widget = None
        self.ml_use_model_plot_widget = None
        self.ml_plotting_extraction = False
        self.ml_plotting_evaluation = False
        self.ml_data = None

        gui_inarg = GUIArgumentParser()
        if under_test:
            self.args = gui_inarg.parse_args([])
        else:
            self.args = gui_inarg.parse_args()

        self.set_gui_state("ml_mode", self.args.machine_learning)
        self.sig_sensor_config_pidget_event.connect(
            self.pidget_sensor_config_event_handler)
        self.sig_processing_config_pidget_event.connect(
            self.pidget_processing_config_event_handler)

        self.module_label_to_sensor_config_map = {}
        self.module_label_to_processing_config_map = {}
        self.current_module_info = MODULE_INFOS[0]
        for mi in MODULE_INFOS:
            if mi.sensor_config_class is not None:
                self.module_label_to_sensor_config_map[mi.label] = mi.sensor_config_class()

                processing_config = self.get_default_processing_config(mi.label)
                self.module_label_to_processing_config_map[mi.label] = processing_config

        self.setWindowIcon(QIcon(self.ACC_IMG_FILENAME))

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
        self.init_pidgets()

        if self.get_gui_state("ml_mode"):
            self.init_machine_learning()
            self.main_widget.addWidget(self.tab_parent)
            self.canvas_layout = self.tabs["collect"].layout
        else:
            self.canvas_widget = QFrame(self.main_widget)
            self.canvas_layout = QtWidgets.QVBoxLayout(self.canvas_widget)

        self.main_widget.addWidget(self.panel_scroll_area)

        self.update_canvas(force_update=True)

        self.resize(1200, 800)
        self.setWindowTitle("Acconeer Exploration GUI")
        self.show()
        self.start_up()
        lib_version_up_to_date(gui_handle=self)

        self.radar = data_processing.DataProcessing()

    def init_pyqtgraph(self):
        pg.setConfigOption("background", "#f0f0f0")
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("leftButtonPan", False)
        pg.setConfigOptions(antialias=True)

    def init_labels(self):
        # key: (text)
        label_info = {
            "sensor": ("Sensor",),
            "sweep_buffer": ("Sweep buffer",),
            "interface": ("Interface",),
            "sweep_info": ("",),
            "saturated": ("Warning: Data saturated, reduce gain!",),
            "libver": ("",),
        }

        self.labels = {}
        for key, (text,) in label_info.items():
            lbl = QLabel(self)
            lbl.setText(text)
            self.labels[key] = lbl

        self.labels["saturated"].setStyleSheet("color: #f0f0f0")

    def init_textboxes(self):
        # key: (text)
        textbox_info = {
            "host": ("192.168.1.100",),
            "sweep_buffer": ("100",),
            "sweep_buffer_ml": ("unlimited",),
        }

        self.textboxes = {}
        for key, (text,) in textbox_info.items():
            self.textboxes[key] = QLineEdit(self)
            self.textboxes[key].setText(text)

        self.textboxes["sweep_buffer_ml"].setVisible(False)
        self.textboxes["sweep_buffer_ml"].setEnabled(False)

    def init_checkboxes(self):
        # text, status, visible, enabled, function
        checkbox_info = {
            "verbose": ("Verbose logging", False, True, True, self.set_log_level),
            "opengl": ("OpenGL", False, True, True, self.enable_opengl),
        }

        self.checkboxes = {}
        for key, (text, status, visible, enabled, fun) in checkbox_info.items():
            cb = QCheckBox(text, self)
            cb.setChecked(status)
            cb.setVisible(visible)
            cb.setEnabled(enabled)
            if fun:
                cb.stateChanged.connect(fun)
            self.checkboxes[key] = cb

    def init_graphs(self, refresh=False):
        processing_config = self.get_default_processing_config()

        if self.current_module_info.module is None:
            canvas = Label(self.ACC_IMG_FILENAME)
            self.buttons["sensor_defaults"].setEnabled(False)
            self.refresh_pidgets()
            return canvas

        self.buttons["sensor_defaults"].setEnabled(True)

        canvas = pg.GraphicsLayoutWidget()

        if not refresh:
            self.set_multi_sensors()

            if not (processing_config and isinstance(processing_config, dict)):
                self.service_params = None
                self.service_defaults = None
            else:
                self.service_params = processing_config
                self.service_defaults = copy.deepcopy(self.service_params)

            self.add_params(self.service_params)

        if refresh:
            self.save_gui_settings_to_sensor_config()
        else:
            self.load_gui_settings_from_sensor_config()

        self.reload_pg_updater(canvas=canvas)

        self.refresh_pidgets()

        return canvas

    def reload_pg_updater(self, canvas=None, session_info=None):
        if canvas is None:
            canvas = pg.GraphicsLayoutWidget()
            self.swap_canvas(canvas)

        sensor_config = self.get_sensor_config()
        processing_config = self.update_service_params()

        if session_info is None:
            session_info = clients.MockClient().setup_session(sensor_config)

        self.service_widget = self.current_module_info.module.PGUpdater(
            sensor_config, processing_config, session_info)

        self.service_widget.setup(canvas)

    def init_pidgets(self):
        self.last_sensor_config = None

        for sensor_config in self.module_label_to_sensor_config_map.values():
            sensor_config._event_handlers.add(self.pidget_sensor_config_event_handler)
            pidgets = sensor_config._create_pidgets()

            for pidget in pidgets:
                if pidget is None:
                    continue

                category = pidget.param.category
                if category == configbase.Category.ADVANCED:
                    grid = self.advanced_sensor_config_section.grid
                    count = self.advanced_sensor_param_count
                else:
                    grid = self.settings_section.grid
                    count = self.basic_sensor_param_count

                grid.addWidget(pidget, count.val, 0, 1, 2)
                count.post_incr()

        self.last_processing_config = None

        for processing_config in self.module_label_to_processing_config_map.values():
            if not isinstance(processing_config, configbase.Config):
                continue

            processing_config._event_handlers.add(self.pidget_processing_config_event_handler)
            pidgets = processing_config._create_pidgets()

            for pidget in pidgets:
                if pidget is None:
                    continue

                if pidget.param.category == configbase.Category.ADVANCED:
                    grid = self.advanced_processing_config_section.grid
                    count = self.param_grid_count
                else:
                    grid = self.basic_processing_config_section.grid
                    count = self.param_grid_count

                grid.addWidget(pidget, count.val, 0, 1, 2)
                count.post_incr()

        self.refresh_pidgets()

    def refresh_pidgets(self):
        self.refresh_sensor_pidgets()
        self.refresh_processing_pidgets()

    def refresh_sensor_pidgets(self):
        sensor_config = self.get_sensor_config()

        if self.last_sensor_config != sensor_config:
            if self.last_sensor_config is not None:
                self.last_sensor_config._state = configbase.Config.State.UNLOADED

            self.last_sensor_config = sensor_config

        if sensor_config is None:
            self.settings_section.setVisible(False)
            self.advanced_sensor_config_section.setVisible(False)
            return

        sensor_config._state = configbase.Config.State.LOADED

        has_basic_params = has_advanced_params = False
        for param in sensor_config._get_params():
            if param.visible:
                if param.category == configbase.Category.ADVANCED:
                    has_advanced_params = True
                else:
                    has_basic_params = True

        if self.get_gui_state("ml_tab") == "main":
            self.settings_section.setVisible(has_basic_params)
            self.advanced_sensor_config_section.setVisible(has_advanced_params)

    def refresh_processing_pidgets(self):
        processing_config = self.get_processing_config()

        if self.last_processing_config != processing_config:
            if isinstance(self.last_processing_config, configbase.Config):
                self.last_processing_config._state = configbase.Config.State.UNLOADED

            self.last_processing_config = processing_config

        if processing_config is None:
            self.basic_processing_config_section.hide()
            self.advanced_processing_config_section.hide()
            return

        # TODO: remove the follow check when migration to configbase is done
        if not isinstance(processing_config, configbase.Config):
            return

        processing_config._state = configbase.Config.State.LOADED

        has_basic_params = has_advanced_params = False
        for param in processing_config._get_params():
            if param.visible:
                if param.category == configbase.Category.ADVANCED:
                    has_advanced_params = True
                else:
                    has_basic_params = True

        if self.get_gui_state("ml_tab") == "main":
            self.basic_processing_config_section.setVisible(has_basic_params)
            self.advanced_processing_config_section.setVisible(has_advanced_params)

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

    def update_pidgets_on_event(self, sensor_config=None, processing_config=None):
        if sensor_config is None:
            sensor_config = self.get_sensor_config()

            if sensor_config is None:
                return

        if processing_config is None:
            processing_config = self.get_processing_config()

        if isinstance(processing_config, configbase.Config):
            processing_config._update_pidgets()

        if hasattr(processing_config, "check_sensor_config"):
            alerts = processing_config.check_sensor_config(sensor_config)
        else:
            alerts = []

        sensor_config._update_pidgets(alerts)

    def init_dropdowns(self):
        self.module_dd = QComboBox(self)

        for module_info in MODULE_INFOS:
            if self.get_gui_state("ml_mode"):
                if module_info.allow_ml:
                    self.module_dd.addItem(module_info.label)
            else:
                self.module_dd.addItem(module_info.label)

        self.module_dd.currentIndexChanged.connect(self.update_canvas)

        self.interface_dd = QComboBox(self)
        self.interface_dd.addItem("Socket")
        self.interface_dd.addItem("Serial")
        self.interface_dd.addItem("SPI")
        self.interface_dd.addItem("Simulated")
        self.interface_dd.currentIndexChanged.connect(self.update_interface)

        self.ports_dd = QComboBox(self)
        self.ports_dd.hide()
        self.update_ports()

    def enable_opengl(self):
        if self.checkboxes["opengl"].isChecked():
            warning = "Do you really want to enable OpenGL?"
            detailed = "Enabling OpenGL might crash the GUI or introduce graphic glitches!"
            if self.warning_message(warning, detailed_warning=detailed):
                pg.setConfigOptions(useOpenGL=True)
                self.update_canvas(force_update=True)
            else:
                self.checkboxes["opengl"].setChecked(False)
        else:
            pg.setConfigOptions(useOpenGL=False)
            self.update_canvas(force_update=True)

    def set_multi_sensors(self):
        multi_sensor = False
        if self.get_gui_state("has_loaded_data"):
            multi_sensor = len(json.loads(self.data.sensor_config_dump)["sensor"]) > 1
        elif self.multi_sensor_interface:
            multi_sensor = self.current_module_info.multi_sensor

        sensor = self.get_sensors()

        for name in self.sensor_widgets:
            self.sensor_widgets[name].set_multi_sensor_support(multi_sensor)

        if not multi_sensor and self.multi_sensor_interface:
            if isinstance(sensor, list) and len(sensor):
                self.set_sensors(sensor[0])

    def set_sensors(self, sensors):
        for name in self.sensor_widgets:
            self.sensor_widgets[name].set_sensors(sensors)

    def get_sensors(self, widget_name=None):
        if widget_name is None:
            widget_name = "main"

        sensors = self.sensor_widgets[widget_name].get_sensors()

        return sensors

    def update_ports(self):
        port_infos = serial.tools.list_ports.comports()
        ports = [port_info[0] for port_info in port_infos]

        try:
            opsys = os.uname()
            if "microsoft" in opsys.release.lower() and "linux" in opsys.sysname.lower():
                print("WSL detected. Limiting serial ports")
                ports_reduced = []
                for p in ports:
                    if int(re.findall(r"\d+", p)[0]) < 20:
                        ports_reduced.append(p)
                ports = ports_reduced
        except Exception:
            pass

        self.ports_dd.clear()
        self.ports_dd.addItems(ports)

    def advanced_port(self):
        dialog = AdvancedSerialDialog(self.override_baudrate, self)
        ret = dialog.exec_()

        if ret == QtWidgets.QDialog.Accepted:
            self.override_baudrate = dialog.get_state()

        dialog.deleteLater()

    def init_buttons(self):
        # key: text, function, enabled, hidden, group
        button_info = {
            "start": ("Start", self.start_scan, False, False, "scan"),
            "connect": ("Connect", self.connect_to_server, True, False, "connection"),
            "stop": ("Stop", self.stop_scan, False, False, "scan"),
            "load_scan": ("Load Scan", lambda: self.load_scan(), True, False, "scan"),
            "save_scan": ("Save Scan", lambda: self.save_scan(self.data), False, False, "scan"),
            "replay_buffered": (
                "Replay buffered/loaded",
                lambda: self.load_scan(restart=True),
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
        self.server_section.grid.addWidget(self.labels["interface"], 0, 0)
        self.server_section.grid.addWidget(self.interface_dd, 0, 1)
        self.server_section.grid.addWidget(self.ports_dd, 1, 0)
        self.server_section.grid.addWidget(self.textboxes["host"], 1, 0, 1, 2)
        self.server_section.grid.addWidget(self.buttons["scan_ports"], 1, 1)
        self.server_section.grid.addWidget(self.buttons["advanced_port"], 2, 0, 1, 2)
        self.server_section.grid.addWidget(self.buttons["connect"], 3, 0, 1, 2)

        self.control_section = CollapsibleSection("Scan controls")
        self.main_sublayout.addWidget(self.control_section, 1, 0)
        c = self.control_grid_count
        self.control_section.grid.addWidget(self.module_dd, c.pre_incr(), 0, 1, 2)
        self.control_section.grid.addWidget(self.buttons["start"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.buttons["stop"], c.val, 1)
        self.control_section.grid.addWidget(self.buttons["save_scan"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.buttons["load_scan"], c.val, 1)
        self.control_section.grid.addWidget(self.buttons["replay_buffered"], c.pre_incr(), 0, 1, 2)
        self.control_section.grid.addWidget(self.labels["sweep_buffer"], c.pre_incr(), 0)
        self.control_section.grid.addWidget(self.textboxes["sweep_buffer"], c.val, 1)
        self.control_section.grid.addWidget(self.textboxes["sweep_buffer_ml"], c.val, 1)

        self.settings_section = CollapsibleSection("Sensor settings")
        self.main_sublayout.addWidget(self.settings_section, 4, 0)
        c = self.basic_sensor_param_count
        self.settings_section.grid.addWidget(
            self.buttons["sensor_defaults"], c.post_incr(), 0, 1, 2)
        self.settings_section.grid.addWidget(self.labels["sensor"], c.val, 0)

        sensor_selection = SensorSelection(error_handler=self.error_message)
        self.settings_section.grid.addWidget(sensor_selection, c.post_incr(), 1)
        self.sensor_widgets["main"] = sensor_selection
        self.set_multi_sensors()

        self.advanced_sensor_config_section = CollapsibleSection(
            "Advanced sensor settings", init_collapsed=True)
        self.main_sublayout.addWidget(self.advanced_sensor_config_section, 5, 0)

        self.basic_processing_config_section = CollapsibleSection("Processing settings")
        self.main_sublayout.addWidget(self.basic_processing_config_section, 6, 0)
        self.basic_processing_config_section.grid.addWidget(
            self.buttons["service_defaults"], 0, 0, 1, 2)

        self.advanced_processing_config_section = CollapsibleSection(
            "Advanced processing settings", init_collapsed=True)
        self.main_sublayout.addWidget(self.advanced_processing_config_section, 7, 0)
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["advanced_defaults"], 0, 0, 1, 2)
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["load_process_data"], 1, 0)
        self.advanced_processing_config_section.grid.addWidget(
            self.buttons["save_process_data"], 1, 1)

        self.main_sublayout.setRowStretch(7, 1)

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
        self.statusBar().addPermanentWidget(self.labels["saturated"])
        self.statusBar().addPermanentWidget(self.labels["sweep_info"])
        self.statusBar().addPermanentWidget(self.labels["libver"])
        self.statusBar().addPermanentWidget(self.checkboxes["verbose"])
        self.statusBar().addPermanentWidget(self.checkboxes["opengl"])
        self.statusBar().setStyleSheet("QStatusBar{border-top: 1px solid lightgrey;}")
        self.statusBar().show()

    def init_machine_learning(self):
        if self.get_gui_state("ml_mode"):
            import ml_gui_elements as ml_gui
            import feature_processing
            self.ml_elements = ml_gui
            self.ml_external = feature_processing.DataProcessor
            self.ml_module = feature_processing
            self.init_tabs()
            self.init_ml_panels()

    def init_tabs(self):
        self.tab_parent = QTabWidget(self.main_widget)
        self.tab_parent.setStyleSheet("background: #f0f0f0")
        self.tab_parent.resize(300, 200)

        self.tabs = {
            "collect": (QWidget(self.main_widget), "Configure service"),
            "feature_select": (QWidget(self.main_widget), "Feature configuration"),
            "feature_extract": (QWidget(self.main_widget), "Feature extraction"),
            "feature_inspect": (QWidget(self.main_widget), "Feature inspection"),
            "train": (QWidget(self.main_widget), "Train Network"),
            "eval": (QWidget(self.main_widget), "Use Network"),
            }

        self.tabs_text_to_key = {
            "Configure service": "main",
            "Feature configuration": "feature_select",
            "Feature extraction": "feature_extract",
            "Feature inspection": "feature_inspect",
            "Train Network": "train",
            "Use Network": "eval",
        }

        for key, (tab, label) in self.tabs.items():
            self.tab_parent.addTab(tab, label)
            tab.layout = QtWidgets.QVBoxLayout()
            tab.setLayout(tab.layout)
            self.tabs[key] = tab

        self.tab_parent.currentChanged.connect(self.tab_changed)

        self.feature_select = self.ml_elements.FeatureSelectFrame(
            self.main_widget,
            gui_handle=self
            )
        self.tabs["feature_select"].layout.addWidget(self.feature_select)

        self.feature_extract = self.ml_elements.FeatureExtractFrame(
            self.main_widget,
            gui_handle=self
            )
        self.tabs["feature_extract"].layout.addWidget(self.feature_extract)

        self.feature_inspect = self.ml_elements.FeatureInspectFrame(
            self.main_widget,
            gui_handle=self
            )
        self.tabs["feature_inspect"].layout.addWidget(self.feature_inspect)

        self.training = self.ml_elements.TrainingFrame(self.main_widget, gui_handle=self)
        self.tabs["train"].layout.addWidget(self.training)

        self.eval_model = self.ml_elements.EvalFrame(self.main_widget, gui_handle=self)
        self.tabs["eval"].layout.addWidget(self.eval_model)

    def init_ml_panels(self):
        # feature select/extract/inspect frame
        self.feature_section = CollapsibleSection("Feature settings", init_collapsed=False)
        self.main_sublayout.addWidget(self.feature_section, 3, 0)
        self.feature_sidepanel = self.ml_elements.FeatureSidePanel(self.main_widget, self)
        self.feature_section.grid.addWidget(self.feature_sidepanel, 0, 0, 1, 2)
        self.feature_section.hide()
        self.feature_section.button_event(override=False)

        # training frame
        self.training_sidepanel = self.ml_elements.TrainingSidePanel(
            self.panel_scroll_area_widget, self)
        self.panel_scroll_area_widget.addWidget(self.training_sidepanel)

        # eval frame
        self.eval_section = CollapsibleSection("Run model", init_collapsed=False)
        self.main_sublayout.addWidget(self.eval_section, 2, 0)
        self.eval_sidepanel = self.ml_elements.EvalSidePanel(self.eval_section, self)
        self.eval_section.grid.addWidget(self.eval_sidepanel, 0, 0, 1, 2)
        self.eval_section.hide()
        self.eval_section.button_event(override=False)

    def tab_changed(self, index):
        tab = self.tab_parent.tabText(index)
        self.set_gui_state("ml_tab", self.tabs_text_to_key[tab])

    def enable_tabs(self, enable):
        if not self.get_gui_state("ml_mode"):
            return

        current_tab = self.tab_parent.currentIndex()
        for i in range(len(self.tabs)):
            if i != current_tab:
                self.tab_parent.setTabEnabled(i, enable)

    def add_params(self, params, start_up_mode=None):
        if params is None:
            params = {}

        self.buttons["load_process_data"].hide()
        self.buttons["save_process_data"].hide()
        for mode in self.service_labels:
            for param_key in self.service_labels[mode]:
                for element in self.service_labels[mode][param_key]:
                    if element in ["label", "box", "checkbox", "button"]:
                        self.service_labels[mode][param_key][element].setVisible(False)

        if start_up_mode is None:
            mode = self.current_module_label
            set_visible = True
        else:
            mode = start_up_mode
            set_visible = False

        if mode not in self.service_labels:
            self.service_labels[mode] = {}

        advanced_available = False
        for param_key, param_dict in params.items():
            if param_key not in self.service_labels[mode]:
                param_gui_dict = {}
                self.service_labels[mode][param_key] = param_gui_dict

                advanced_available = bool(param_dict.get("advanced"))
                if advanced_available:
                    grid = self.advanced_processing_config_section.grid
                else:
                    grid = self.basic_processing_config_section.grid

                param_gui_dict["advanced"] = advanced_available

                if "send_process_data" == param_key:
                    data_buttons = param_gui_dict
                    data_buttons["load_button"] = self.buttons["load_process_data"]
                    data_buttons["save_button"] = self.buttons["save_process_data"]
                    data_buttons["load_text"] = "Load " + param_dict["text"]
                    data_buttons["save_text"] = "Save " + param_dict["text"]
                    data_buttons["load_button"].setText(data_buttons["load_text"])
                    data_buttons["save_button"].setText(data_buttons["save_text"])
                    data_buttons["load_button"].setVisible(set_visible)
                    data_buttons["save_button"].setVisible(set_visible)
                elif isinstance(param_dict["value"], bool):
                    param_gui_dict["checkbox"] = QCheckBox(param_dict["name"], self)
                    param_gui_dict["checkbox"].setChecked(param_dict["value"])
                    grid.addWidget(param_gui_dict["checkbox"], self.param_grid_count.val, 0, 1, 2)
                elif param_dict["value"] is not None:
                    param_gui_dict["label"] = QLabel(self)
                    param_gui_dict["label"].setMinimumWidth(125)
                    param_gui_dict["label"].setText(param_dict["name"])
                    param_gui_dict["box"] = QLineEdit(self)
                    param_gui_dict["box"].setText(str(param_dict["value"]))
                    param_gui_dict["limits"] = param_dict["limits"]
                    param_gui_dict["default"] = param_dict["value"]
                    grid.addWidget(param_gui_dict["label"], self.param_grid_count.val, 0)
                    grid.addWidget(param_gui_dict["box"], self.param_grid_count.val, 1)
                    param_gui_dict["box"].setVisible(set_visible)
                else:  # param is only a label
                    param_gui_dict["label"] = QLabel(self)
                    param_gui_dict["label"].setText(str(param_dict["text"]))
                    grid.addWidget(param_gui_dict["label"], self.param_grid_count.val, 0, 1, 2)

                self.param_grid_count.post_incr()
            else:
                param_gui_dict = self.service_labels[mode][param_key]

                for element in param_gui_dict:
                    if element in ["label", "box", "checkbox"]:
                        param_gui_dict[element].setVisible(set_visible)
                    if "button" in element:
                        data_buttons = param_gui_dict
                        data_buttons["load_button"].setText(data_buttons["load_text"])
                        data_buttons["save_button"].setText(data_buttons["save_text"])
                        data_buttons["load_button"].setVisible(set_visible)
                        data_buttons["save_button"].setVisible(set_visible)
                    if param_gui_dict["advanced"]:
                        advanced_available = True

        if start_up_mode is None:
            if self.get_gui_state("ml_tab") == "main":
                self.basic_processing_config_section.setVisible(bool(params))

            if advanced_available:
                self.advanced_processing_config_section.show()
                self.advanced_processing_config_section.button_event(override=True)
            else:
                self.advanced_processing_config_section.hide()

    def sensor_defaults_handler(self):
        config = self.get_sensor_config()

        if config is None:
            return

        default_config = self.current_module_info.sensor_config_class()
        config._loads(default_config._dumps())

        self.load_gui_settings_from_sensor_config()  # TODO

    def service_defaults_handler(self):
        processing_config = self.get_processing_config()

        if isinstance(processing_config, configbase.Config):
            processing_config._reset()
            return

        mode = self.current_module_label
        if self.service_defaults is None:
            return
        for key in self.service_defaults:
            if key in self.service_labels[mode]:
                if "box" in self.service_labels[mode][key]:
                    self.service_labels[mode][key]["box"].setText(
                        str(self.service_defaults[key]["value"]))
                if "checkbox" in self.service_labels[mode][key]:
                    self.service_labels[mode][key]["checkbox"].setChecked(
                        bool(self.service_defaults[key]["value"]))

    def update_canvas(self, force_update=False):
        module_label = self.module_dd.currentText()
        switching_module = self.current_module_label != module_label
        self.current_module_label = module_label

        self.current_module_info = MODULE_LABEL_TO_MODULE_INFO_MAP[module_label]

        if self.current_module_info.module is None:
            data_type = None
            self.external = None
        else:
            data_type = self.current_module_info.sensor_config_class().mode
            self.external = self.current_module_info.processor

        switching_data_type = self.current_data_type != data_type
        self.current_data_type = data_type

        if switching_data_type:
            self.data = None
            self.set_gui_state("has_loaded_data", False)
            self.buttons["replay_buffered"].setEnabled(False)

        if force_update or switching_module:
            if not switching_module:
                self.update_service_params()

            new_canvas = self.init_graphs(refresh=(not switching_module))
            self.swap_canvas(new_canvas)

        self.load_gui_settings_from_sensor_config()

    def swap_canvas(self, new_canvas):
        if self.canvas is not None:
            self.canvas_layout.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()

        self.canvas_layout.addWidget(new_canvas)
        self.canvas = new_canvas

    def update_interface(self):
        if self.gui_states["server_connected"]:
            self.connect_to_server()

        self.multi_sensor_interface = True
        if "serial" in self.interface_dd.currentText().lower():
            self.ports_dd.show()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].show()
            self.buttons["scan_ports"].show()
            self.update_ports()
            self.multi_sensor_interface = False
        elif "spi" in self.interface_dd.currentText().lower():
            self.ports_dd.hide()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()
            self.multi_sensor_interface = False
        elif "socket" in self.interface_dd.currentText().lower():
            self.ports_dd.hide()
            self.textboxes["host"].show()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()
        elif "simulated" in self.interface_dd.currentText().lower():
            self.ports_dd.hide()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()

        self.set_multi_sensors()

    def error_message(self, error):
        em = QtWidgets.QErrorMessage(self.main_widget)
        em.setWindowTitle("Error")
        em.showMessage(error.replace("\n", "<br>"))

    def info_handle(self, info, detailed_info=None):
        msg = QtWidgets.QMessageBox(self.main_widget)
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setText(info)
        if detailed_info:
            msg.setDetailedText(detailed_info)
        msg.setWindowTitle("Info")
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg.exec_()

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
        if self.get_gui_state("has_loaded_data") and not from_file:
            self.set_gui_state("has_loaded_data", False)
        if self.current_module_info.module is None:
            self.error_message("Please select a service or detector")
            return

        try:
            self.sweep_buffer = int(self.textboxes["sweep_buffer"].text())
        except Exception:
            self.error_message("Sweep buffer needs to be a positive integer\n")
        else:
            self.sweep_buffer = 500
            self.textboxes["sweep_buffer"].setText("500")

        sensor_config = self.get_sensor_config()

        if from_file:
            sensor_config._loads(self.data.sensor_config_dump)
            self.set_gui_state("replaying_data", True)

        self.update_canvas(force_update=True)

        processing_config = self.update_service_params()
        sensor_config = self.save_gui_settings_to_sensor_config()

        sweep_buffer = self.sweep_buffer
        feature_list = None
        ml_plotting = False
        ml_mode = self.get_gui_state("ml_tab")
        if ml_mode != "main":
            is_eval_mode = (ml_mode == "eval")
            ml_plotting = True
            if is_eval_mode:
                if self.eval_sidepanel.model_loaded() is False:
                    self.error_message("Please load a model first!\n")
                    return
                frame_settings = self.eval_sidepanel.get_frame_settings()
                feature_list = self.eval_sidepanel
                sensor = sensor_config.sensor.copy()
                sensor_config = self.eval_sidepanel.get_sensor_config()
                sensor_config.sensor = sensor
                if not self.eval_sidepanel.config_is_valid():
                    return
            else:
                frame_settings = self.feature_sidepanel.get_frame_settings()
                sweep_buffer = np.inf
                feature_list = self.feature_select

            e_handle = self.error_message
            if not self.feature_select.check_limits(sensor_config, error_handle=e_handle):
                return

            if ml_mode == "feature_select":
                frame_settings["frame_pad"] = 0
                frame_settings["collection_mode"] = "continuous"
                frame_settings["rolling"] = True

            processing_config["ml_settings"] = {
                "feature_list": feature_list,
                "frame_settings": frame_settings,
                "evaluate": is_eval_mode,
            }

            if ml_mode == "eval":
                self.ml_use_model_plot_widget.reset_data(sensor_config, processing_config)
            elif ml_mode == "feature_extract":
                self.ml_feature_plot_widget.reset_data(sensor_config, processing_config)

        params = {
            "sensor_config": sensor_config,
            "data_source": "file" if from_file else "stream",
            "module_info": self.current_module_info,
            "sweep_buffer": sweep_buffer,
            "service_params": processing_config,
            "ml_plotting": ml_plotting,
            "multi_sensor": self.current_module_info.multi_sensor,
            "rss_version": getattr(self, "rss_version", None),
        }

        self.threaded_scan = Threaded_Scan(params, parent=self)
        self.threaded_scan.sig_scan.connect(self.thread_receive)
        self.sig_scan.connect(self.threaded_scan.receive)

        self.buttons["start"].setEnabled(False)
        self.buttons["load_scan"].setEnabled(False)
        self.buttons["save_scan"].setEnabled(False)
        self.module_dd.setEnabled(False)
        self.buttons["stop"].setEnabled(True)
        self.checkboxes["opengl"].setEnabled(False)

        self.num_recv_frames = 0
        self.num_missed_frames = 0
        self.threaded_scan.start()

        self.settings_section.body_widget.setEnabled(False)

        if isinstance(processing_config, configbase.Config):
            self.basic_processing_config_section.body_widget.setEnabled(True)
            self.buttons["service_defaults"].setEnabled(False)
            self.buttons["advanced_defaults"].setEnabled(False)
            processing_config._state = configbase.Config.State.LIVE
        else:
            self.basic_processing_config_section.body_widget.setEnabled(False)

        self.buttons["connect"].setEnabled(False)
        self.buttons["replay_buffered"].setEnabled(False)
        self.enable_tabs(False)

        self.set_gui_state("scan_is_running", True)

        if self.get_gui_state("ml_mode"):
            self.feature_select.buttons["stop"].setEnabled(True)
            self.feature_select.buttons["start"].setEnabled(False)
            self.feature_select.buttons["replay_buffered"].setEnabled(False)
            self.feature_sidepanel.textboxes["sweep_rate"].setEnabled(False)

    def set_gui_state(self, state, val):
        if state in self.gui_states:
            self.gui_states[state] = val
        else:
            print("{} is an unknown state!".format(state))
            return

        if state == "server_connected":
            connected = val
            if connected:
                self.buttons["start"].setEnabled(True)
                self.buttons["connect"].setText("Disconnect")
                self.buttons["connect"].setStyleSheet("QPushButton {color: red}")
                self.buttons["advanced_port"].setEnabled(False)
                self.buttons["replay_buffered"].setEnabled(False)
                self.gui_states["has_loaded_data"] = False
                self.data = None
                self.set_multi_sensors()
                if self.get_gui_state("ml_mode"):
                    self.feature_select.update_sensors(self.save_gui_settings_to_sensor_config())
                    if self.feature_select.is_config_valid():
                        self.feature_select.buttons["start"].setEnabled(True)
            else:
                self.buttons["connect"].setText("Connect")
                self.buttons["connect"].setStyleSheet("QPushButton {color: black}")
                self.buttons["start"].setEnabled(False)
                self.buttons["advanced_port"].setEnabled(True)
                self.statusBar().showMessage("Not connected")

        if state == "has_loaded_data":
            if not val:
                self.buttons["replay_buffered"].setEnabled(False)
            self.init_graphs()

        if state == "ml_tab":
            tab = val
            self.feature_sidepanel.select_mode(val)
            self.settings_section.body_widget.setEnabled(True)
            self.server_section.hide()
            self.basic_processing_config_section.hide()
            self.settings_section.hide()
            self.control_section.hide()
            self.feature_section.hide()
            self.eval_section.hide()
            self.textboxes["sweep_buffer_ml"].hide()
            self.textboxes["sweep_buffer"].hide()
            self.module_dd.show()

            if tab == "main":
                if "Select service" not in self.current_module_label:
                    self.basic_processing_config_section.show()
                self.settings_section.show()
                self.server_section.show()
                self.control_section.show()
                self.textboxes["sweep_buffer"].show()
                self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)

            elif tab == "feature_select":
                self.feature_section.button_event(override=False)
                self.settings_section.show()
                self.feature_section.show()
                self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)
                self.set_sensors(self.get_sensors(widget_name="main"))
                self.feature_sidepanel.textboxes["sweep_rate"].setText(
                    self.textboxes["sweep_rate"].text()
                    )
                self.feature_select.check_limits()

            elif tab == "feature_extract":
                self.server_section.show()
                self.control_section.show()
                self.feature_section.button_event(override=False)
                self.feature_section.show()
                self.buttons["start"].setText("Start extraction")
                self.textboxes["sweep_buffer_ml"].show()
                self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)
                self.set_sensors(self.get_sensors(widget_name="main"))
                self.feature_sidepanel.textboxes["sweep_rate"].setText(
                    self.textboxes["sweep_rate"].text()
                    )

                if self.ml_feature_plot_widget is None:
                    self.feature_extract.init_graph()
                    self.ml_feature_plot_widget = self.feature_extract.plot_widget

            elif tab == "feature_inspect":
                self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)
                self.feature_section.show()
                self.feature_inspect.update_frame("frames", 1, init=True)
                self.feature_inspect.update_sliders()

            elif tab == "train":
                self.panel_scroll_area_widget.setCurrentWidget(self.training_sidepanel)

            elif tab == "eval":
                self.settings_section.body_widget.setEnabled(False)
                self.feature_section.show()
                self.eval_section.show()
                self.settings_section.show()
                self.server_section.show()
                self.control_section.show()
                self.textboxes["sweep_buffer"].show()
                self.panel_scroll_area_widget.setCurrentWidget(self.main_sublayout_widget)

                if self.ml_use_model_plot_widget is None:
                    self.eval_model.init_graph()
                    self.ml_use_model_plot_widget = self.eval_model.plot_widget

    def get_gui_state(self, state):
        if state in self.gui_states:
            return self.gui_states[state]
        else:
            print("{} is an unknown state!".format(state))
            return

    def stop_scan(self):
        self.sig_scan.emit("stop", "", None)
        self.buttons["load_scan"].setEnabled(True)
        self.module_dd.setEnabled(True)
        self.buttons["stop"].setEnabled(False)
        self.buttons["connect"].setEnabled(True)
        self.buttons["start"].setEnabled(True)
        self.basic_processing_config_section.body_widget.setEnabled(True)

        if self.get_gui_state("ml_tab") in ["main", "feature_select"]:
            self.settings_section.body_widget.setEnabled(True)

        if self.get_gui_state("ml_mode"):
            self.feature_select.buttons["start"].setEnabled(True)
            self.feature_select.buttons["stop"].setEnabled(False)
            self.feature_sidepanel.textboxes["sweep_rate"].setEnabled(True)
            if self.data is not None:
                self.feature_select.buttons["replay_buffered"].setEnabled(True)

        processing_config = self.get_processing_config()
        if isinstance(processing_config, configbase.Config):
            self.buttons["service_defaults"].setEnabled(True)
            self.buttons["advanced_defaults"].setEnabled(True)
            processing_config._state = configbase.Config.State.LOADED

        self.checkboxes["opengl"].setEnabled(True)
        if self.data is not None:
            self.buttons["replay_buffered"].setEnabled(True)
            self.buttons["save_scan"].setEnabled(True)
        self.set_gui_state("replaying_data", False)
        self.enable_tabs(True)

        self.set_gui_state("scan_is_running", False)

    def set_log_level(self):
        log_level = logging.INFO
        if self.checkboxes["verbose"].isChecked():
            log_level = logging.DEBUG
        utils.set_loglevel(log_level)

    def connect_to_server(self):
        if not self.get_gui_state("server_connected"):
            max_num = 4
            if self.current_module_info.module is None:
                self.module_dd.setCurrentIndex(1)

            if self.interface_dd.currentText().lower() == "socket":
                host = self.textboxes["host"].text()
                self.client = clients.SocketClient(host)
                statusbar_connection_info = "socket ({})".format(host)
            elif self.interface_dd.currentText().lower() == "spi":
                self.client = clients.SPIClient()
                statusbar_connection_info = "SPI"
                max_num = 1
            elif self.interface_dd.currentText().lower() == "simulated":
                self.client = clients.MockClient()
                statusbar_connection_info = "simulated interface"
            else:
                port = self.ports_dd.currentText()
                if "scan" in port.lower():
                    self.error_message("Please select port first!")
                    return

                if self.override_baudrate:
                    print("Warning: Overriding baudrate ({})!".format(self.override_baudrate))

                self.client = clients.UARTClient(port, override_baudrate=self.override_baudrate)
                max_num = 1
                statusbar_connection_info = "UART ({})".format(port)

            self.client.squeeze = False

            try:
                info = self.client.connect()
            except Exception as e:
                err_message = "Could not connect to server!<br>{}".format(e)
                if type(e).__name__ == "SerialException":
                    err_message = "Did you select the right COM port?<br>"
                    err_message += "Try unplugging and plugging back in the module!<br>"
                    err_message += "{}".format(e)
                self.error_message(err_message)
                return

            self.rss_version = info.get("version_str", None)
            max_num = info.get("board_sensor_count", max_num)

            conf = self.get_sensor_config()
            sensor = 1
            sensors_available = []
            connection_success = False
            error = None
            while sensor <= max_num:
                conf.sensor = sensor
                try:
                    self.client.setup_session(conf)
                    self.client.start_session()
                    self.client.stop_session()
                    connection_success = True
                    sensors_available.append(sensor)
                except Exception as e:
                    print("Sensor {:d} not available".format(sensor))
                    error = e
                sensor += 1
            if connection_success:
                self.set_sensors(sensors_available)
                self.set_gui_state("server_connected", True)
                self.statusBar().showMessage("Connected via {}".format(statusbar_connection_info))
            else:
                self.error_message("Could not connect to server!\n{}".format(error))
                return
        else:
            self.set_gui_state("server_connected", False)
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

    def update_service_params(self):
        if isinstance(self.get_processing_config(), configbase.Config):
            return self.get_processing_config()

        errors = []
        mode = self.current_module_label

        if mode not in self.service_labels:
            return None

        for key in self.service_labels[mode]:
            entry = self.service_labels[mode][key]
            if "box" in entry:
                er = False
                val = self.is_float(entry["box"].text(),
                                    is_positive=False)
                limits = entry["limits"]
                default = entry["default"]
                if val is not False:
                    val, er = self.check_limit(val, entry["box"],
                                               limits[0], limits[1], set_to=default)
                else:
                    er = True
                    val = default
                    entry["box"].setText(str(default))
                if er:
                    errors.append("{:s} must be between {:s} and {:s}!\n".format(
                        key, str(limits[0]), str(limits[1])))
                self.service_params[key]["value"] = self.service_params[key]["type"](val)
            elif "checkbox" in entry:
                self.service_params[key]["value"] = entry["checkbox"].isChecked()

            if "send_process_data" in key:
                if self.advanced_process_data["use_data"]:
                    if self.advanced_process_data["process_data"] is not None:
                        data = self.advanced_process_data["process_data"]
                        self.service_params["send_process_data"]["value"] = data
                    else:
                        data = self.service_params["send_process_data"]["text"]
                        print(data + " data not available")
                else:
                    self.service_params["send_process_data"]["value"] = None

        if len(errors):
            self.error_message("".join(errors))

        return self.service_params

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
            self.start_scan(from_file=True)
            return

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Load scan",
                "",
                "HDF5 data files (*.h5);; NumPy data files (*.npz)",
                options=options
                )

        if not filename:
            return

        try:
            record = recording.load(filename)
        except Exception as e:
            traceback.print_exc()
            self.error_message("Failed to load file:\n {:s}".format(e))
            return

        try:
            module_info = MODULE_KEY_TO_MODULE_INFO_MAP[record.module_key]
            index = self.module_dd.findText(module_info.label, QtCore.Qt.MatchFixedString)
        except Exception:
            has_loaded_module = False
            print("Can't find the module for the loaded data")
        else:
            has_loaded_module = True

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

        self.set_multi_sensors()
        self.set_sensors(sensor_config.sensor)

        if has_loaded_module:
            processing_config = self.get_processing_config()
            if isinstance(processing_config, configbase.ProcessingConfig):
                if record.processing_config_dump is not None:
                    processing_config._loads(record.processing_config_dump)

        self.set_gui_state("has_loaded_data", True)
        self.start_scan(from_file=True)

    def save_scan(self, record):
        if len(record.data) == 0:
            self.error_message("No data to save")
            return

        if "sleep" in self.current_module_label.lower():
            if int(self.textboxes["sweep_buffer"].text()) < 1000:
                self.error_message("Please set sweep buffer to >= 1000")
                return

        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog
        title = "Save scan"
        file_types = "HDF5 data files (*.h5);; NumPy data files (*.npz)"
        filename, info = QtWidgets.QFileDialog.getSaveFileName(
                self, title, "", file_types, options=options)

        if not filename:
            return

        try:
            if "h5" in info:
                recording.save_h5(filename, record)
            else:
                recording.save_npz(filename, record)
        except Exception as e:
            traceback.print_exc()
            self.error_message("Failed to save file:\n {:s}".format(e))

    def handle_advanced_process_data(self, action=None):
        load_text = self.buttons["load_process_data"].text()
        try:
            data_text = self.service_params["send_process_data"]["text"]
        except Exception as e:
            print("Function not available! \n{}".format(e))
            return

        if action == "save":
            if self.advanced_process_data["process_data"] is not None:
                options = QtWidgets.QFileDialog.Options()
                options |= QtWidgets.QFileDialog.DontUseNativeDialog

                title = "Save " + load_text
                file_types = "NumPy data files (*.npy)"
                fname, info = QtWidgets.QFileDialog.getSaveFileName(
                    self, title, "", file_types, options=options)
                if fname:
                    try:
                        np.save(fname, self.advanced_process_data["process_data"])
                    except Exception as e:
                        self.error_message("Failed to save " + load_text + "{}".format(e))
                        return
                    self.advanced_process_data["use_data"] = True
                    self.buttons["load_process_data"].setText(load_text.replace("Load", "Unload"))
                    self.buttons["load_process_data"].setStyleSheet("QPushButton {color: red}")
            else:
                self.error_message(data_text + " data not availble!".format())
        elif action == "load":
            if "Unload" in load_text:
                self.buttons["load_process_data"].setText(load_text.replace("Unload", "Load"))
                self.buttons["load_process_data"].setStyleSheet("QPushButton {color: black}")
                self.advanced_process_data["use_data"] = False
            else:
                options = QtWidgets.QFileDialog.Options()
                options |= QtWidgets.QFileDialog.DontUseNativeDialog
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self, "Load " + data_text, "", "NumPy data Files (*.npy)", options=options)
                if fname:
                    try:
                        content = np.load(fname, allow_pickle=True)
                        self.advanced_process_data["process_data"] = content
                    except Exception as e:
                        self.error_message("Failed to load " + data_text + "\n{}".format(e))
                        return
                    self.advanced_process_data["use_data"] = True
                    self.buttons["load_process_data"].setText(load_text.replace("Load", "Unload"))
                    self.buttons["load_process_data"].setStyleSheet("QPushButton {color: red}")
        else:
            print("Process data action not implemented")

    def thread_receive(self, message_type, message, data=None):
        if "error" in message_type:
            if "client" in message_type:
                self.stop_scan()
                if self.get_gui_state("server_connected"):
                    self.connect_to_server()
                self.buttons["start"].setEnabled(False)
            elif "proccessing" in message_type:
                self.stop_scan()
            self.error_message("{}".format(message))
        elif message_type == "scan_data":
            if not self.get_gui_state("replaying_data"):
                self.data = data
        elif message_type == "scan_done":
            self.stop_scan()
            if not self.get_gui_state("server_connected"):
                self.buttons["start"].setEnabled(False)
        elif "update_external_plots" in message_type:
            if data is not None:
                self.update_external_plots(data)
        elif "sweep_info" in message_type:
            self.update_sweep_info(data)
        elif "session_info" in message_type:
            self.session_info = data
            self.reload_pg_updater(session_info=data)
        elif "process_data" in message_type:
            self.advanced_process_data["process_data"] = data
        elif "set_sensors" in message_type:
            self.set_sensors(data)
        else:
            print("Thread data not implemented!")
            print(message_type, message, data)

    def update_external_plots(self, data):
        if isinstance(data, dict) and data.get("ml_plotting") is True:
            if self.get_gui_state("ml_tab") == "feature_extract":
                self.ml_feature_plot_widget.update(data)
            elif self.get_gui_state("ml_tab") == "feature_select":
                self.feature_select.plot_feature(data)
            elif self.get_gui_state("ml_tab") == "eval":
                self.ml_use_model_plot_widget.update(data)
            self.ml_data = data
        else:
            self.service_widget.update(data)

    def update_sweep_info(self, infos):
        if not isinstance(infos, list):  # If squeezed
            infos = [infos]

        missed = any([e.get("missed_data", False) for e in infos])
        saturated = any([e.get("data_saturated", False) for e in infos])

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

        self.labels["saturated"].setVisible(saturated)

    def start_up(self):
        if not self.under_test:
            if os.path.isfile(self.LAST_CONF_FILENAME):
                try:
                    last = np.load(self.LAST_CONF_FILENAME, allow_pickle=True)
                    self.load_last_config(last.item())
                except Exception as e:
                    print("Could not load settings from last session\n{}".format(e))
            if os.path.isfile(self.LAST_ML_CONF_FILENAME) and self.get_gui_state("ml_mode"):
                try:
                    last = np.load(self.LAST_ML_CONF_FILENAME, allow_pickle=True)
                    self.feature_select.update_feature_list(last.item()["feature_list"])
                    self.feature_sidepanel.set_frame_settings(last.item()["frame_settings"])
                except Exception as e:
                    print("Could not load ml settings from last session\n{}".format(e))

    def load_last_config(self, last_config):
        # Restore sensor configs (configbase)
        dumps = last_config.get("sensor_config_dumps", {})
        for key, conf in self.module_label_to_sensor_config_map.items():
            if key in dumps:
                dump = last_config["sensor_config_dumps"][key]
                try:
                    conf._loads(dump)
                except Exception:
                    print("Could not load sensor config for \'{}\'".format(key))
                    conf._reset()  # TODO: load module defaults

        # Restore processing configs (configbase)
        dumps = last_config.get("processing_config_dumps", {})
        for key, conf in self.module_label_to_processing_config_map.items():
            if key in dumps:
                dump = last_config["processing_config_dumps"][key]
                try:
                    conf._loads(dump)
                except Exception:
                    print("Could not load processing config for \'{}\'".format(key))
                    conf._reset()

        # Restore misc. settings
        self.textboxes["sweep_buffer"].setText(last_config["sweep_buffer"])
        self.interface_dd.setCurrentIndex(last_config["interface"])
        self.ports_dd.setCurrentIndex(last_config["port"])
        self.textboxes["host"].setText(last_config["host"])

        if last_config.get("override_baudrate"):
            self.override_baudrate = last_config["override_baudrate"]

        # Restore processing configs (legacy)
        if last_config["service_settings"]:
            for module_label in last_config["service_settings"]:
                processing_config = self.get_default_processing_config(module_label)

                if isinstance(processing_config, configbase.Config):
                    continue

                self.add_params(processing_config, start_up_mode=module_label)

                labels = last_config["service_settings"][module_label]
                for key in labels:
                    if "checkbox" in labels[key]:
                        checked = labels[key]["checkbox"]
                        self.service_labels[module_label][key]["checkbox"].setChecked(checked)
                    elif "box" in labels[key]:
                        text = str(labels[key]["box"])
                        self.service_labels[module_label][key]["box"].setText(text)

    def closeEvent(self, event=None):
        # Legacy processing params
        service_params = {}
        for mode in self.service_labels:
            if service_params.get(mode) is None:
                service_params[mode] = {}
            for key in self.service_labels[mode]:
                if service_params[mode].get(key) is None:
                    service_params[mode][key] = {}
                    if "checkbox" in self.service_labels[mode][key]:
                        checked = self.service_labels[mode][key]["checkbox"].isChecked()
                        service_params[mode][key]["checkbox"] = checked
                    elif "box" in self.service_labels[mode][key]:
                        val = self.service_labels[mode][key]["box"].text()
                        service_params[mode][key]["box"] = val

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
            "service_settings": service_params,
            "override_baudrate": self.override_baudrate,
        }

        if not self.under_test:
            np.save(self.LAST_CONF_FILENAME, last_config, allow_pickle=True)

            if self.get_gui_state("ml_mode"):
                try:
                    last_ml_config = {
                        "feature_list": self.feature_select.get_feature_list(),
                        "frame_settings": self.feature_sidepanel.get_frame_settings(),
                    }
                except Exception:
                    pass
                else:
                    np.save(self.LAST_ML_CONF_FILENAME, last_ml_config, allow_pickle=True)

        try:
            self.client.disconnect()
        except Exception:
            pass

        self.close()

    def get_sensor_config(self):
        module_info = self.current_module_info

        if module_info.module is None:
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

        if module_info.module is None:
            return None

        module_label = module_info.label
        return self.module_label_to_processing_config_map[module_label]

    def get_default_processing_config(self, module_label=None):
        if module_label is not None:
            module_info = MODULE_LABEL_TO_MODULE_INFO_MAP[module_label]
        else:
            module_info = self.current_module_info

        module = module_info.module

        if module is None or not hasattr(module, "get_processing_config"):
            return {}

        return module.get_processing_config()


class Threaded_Scan(QtCore.QThread):
    sig_scan = pyqtSignal(str, str, object)

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
                self.emit("session_info", "", session_info)
                self.radar.prepare_processing(self, self.params, session_info)
                self.client.start_session()
            except Exception as e:
                traceback.print_exc()
                self.emit("client_error", "Failed to setup streaming!\n"
                          "{}".format(self.format_error(e)))
                self.running = False

            try:
                while self.running:
                    info, sweep = self.client.get_next()
                    self.emit("sweep_info", "", info)
                    _, record = self.radar.process(sweep, info)
            except Exception as e:
                traceback.print_exc()
                msg = "Failed to communicate with server!\n{}".format(self.format_error(e))
                self.emit("client_error", msg)

            try:
                self.client.stop_session()
            except Exception:
                pass

            if record is not None and len(record.data) > 0:
                self.emit("scan_data", "", record)
        elif self.params["data_source"] == "file":
            self.emit("session_info", "ok", self.data.session_info)

            try:
                self.radar.prepare_processing(self, self.params, self.data.session_info)
                self.radar.process_saved_data(self.data, self)
            except Exception as e:
                traceback.print_exc()
                error = self.format_error(e)
                self.emit("processing_error", "Error while replaying data:<br>" + error)
        else:
            self.emit("error", "Unknown mode %s!" % self.mode)
        self.emit("scan_done", "", "")

    def receive(self, message_type, message, data=None):
        if message_type == "stop":
            if self.running:
                self.running = False
                self.radar.abort_processing()
        elif message_type == "update_feature_extraction":
            self.radar.update_feature_extraction(message, data)
        elif message_type == "update_feature_list":
            self.radar.update_feature_list(data)
        else:
            print("Scan thread received unknown signal: {}".format(message_type))

    def emit(self, message_type, message, data=None):
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


if __name__ == "__main__":
    if lib_version_up_to_date():
        utils.config_logging(level=logging.INFO)

        app = QApplication(sys.argv)
        ex = GUI()

        signal.signal(signal.SIGINT, lambda *_: sigint_handler(ex))

        # Makes sure the signal is caught
        timer = QtCore.QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(200)

        sys.exit(app.exec_())
