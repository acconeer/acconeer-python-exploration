import os
import re
import sys
import ntpath
import numpy as np
import serial.tools.list_ports
import h5py
import logging
import signal
import threading
import copy

from PyQt5.QtWidgets import (QComboBox, QMainWindow, QApplication, QWidget, QLabel, QLineEdit,
                             QCheckBox, QFrame, QPushButton)
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtCore, QtWidgets

from matplotlib.colors import LinearSegmentedColormap

import pyqtgraph as pg

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils

sys.path.append(os.path.dirname(__file__))  # noqa: E402
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))  # noqa: E402

import data_processing
from helper import Label, CollapsibleSection

import service_modules.envelope as env
import service_modules.iq as iq
import examples.processing.presence_detection_iq as prd
import examples.processing.presence_detection_sparse as psd
import examples.processing.phase_tracking as pht
import examples.processing.breathing as br
import examples.processing.sleep_breathing as sb
import examples.processing.obstacle_detection as od


if "win32" in sys.platform.lower():
    import ctypes
    myappid = "acconeer.exploration.tool"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


class GUI(QMainWindow):
    DEFAULT_BAUDRATE = 3000000

    num = 0
    sig_scan = pyqtSignal(str, str, object)
    cl_file = False
    data = None
    client = None
    sweep_count = -1
    acc_file = os.path.join(os.path.dirname(__file__), "acc.png")
    last_file = os.path.join(os.path.dirname(__file__), "last_config.npy")
    sweep_buffer = 500
    cl_supported = False
    sweep_number = 0
    sweeps_skipped = 0
    service_labels = {}
    service_params = None
    service_defaults = None
    advanced_process_data = {"use_data": False, "process_data": None}
    max_cl_sweeps = 10000
    creating_cl = False
    baudrate = DEFAULT_BAUDRATE

    def __init__(self):
        super().__init__()

        self.current_mode = None
        self.current_module_label = None
        self.canvas = None

        self.setWindowIcon(QIcon(self.acc_file))

        self.init_pyqtgraph()
        self.init_labels()
        self.init_textboxes()
        self.init_buttons()
        self.init_dropdowns()
        self.init_checkboxes()
        self.init_sublayouts()
        self.init_panel_scroll_area()
        self.init_statusbar()

        self.main_widget = QtWidgets.QSplitter(self.centralWidget())
        self.main_widget.setStyleSheet("QSplitter::handle{background: lightgrey}")
        self.setCentralWidget(self.main_widget)

        self.canvas_widget = QFrame(self.main_widget)
        self.canvas_widget.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.panel_scroll_area.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.main_widget.addWidget(self.panel_scroll_area)

        self.canvas_layout = QtWidgets.QVBoxLayout(self.canvas_widget)

        self.update_canvas(force_update=True)

        self.resize(1200, 800)
        self.setWindowTitle("Acconeer Exploration GUI")
        self.show()
        self.start_up()

        self.radar = data_processing.DataProcessing()

    def init_pyqtgraph(self):
        pg.setConfigOption("background", "#f0f0f0")
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("leftButtonPan", False)
        pg.setConfigOptions(antialias=True)

    def init_labels(self):
        # key: text, group
        label_info = {
            "sensor": ("Sensor", "sensor"),
            "gain": ("Gain", "sensor"),
            "sweep_rate": ("Sweep frequency", "sensor"),
            "sweeps": ("Number of sweeps", "sensor"),
            "sweep_buffer": ("Sweep buffer", "scan"),
            "range_start": ("Start (m)", "sensor"),
            "range_end": ("Stop (m)", "sensor"),
            "clutter": ("Background settings", "scan"),
            "clutter_status": ("", "scan"),
            "interface": ("Interface", "connection"),
            "power_bins": ("Power bins", "sensor"),
            "subsweeps": ("Subsweeps", "sensor"),
            "sweep_info": ("", "statusbar"),
            "saturated": ("Warning: Data saturated, reduce gain!", "statusbar"),
            "stitching": ("Experimental stitching enabled!", "sensor"),
            "empty_02": ("", "scan"),
        }

        self.labels = {}
        for key, (text, _) in label_info.items():
            lbl = QLabel(self)
            lbl.setText(text)
            self.labels[key] = lbl

        self.labels["power_bins"].setVisible(False)
        self.labels["subsweeps"].setVisible(False)
        self.labels["saturated"].setStyleSheet("color: #f0f0f0")
        self.labels["stitching"].setVisible(False)
        self.labels["stitching"].setStyleSheet("color: red")
        self.labels["clutter_status"].setStyleSheet("color: red")
        self.labels["clutter_status"].setVisible(False)
        self.labels["empty_02"].hide()

    def init_textboxes(self):
        # key: text, group
        textbox_info = {
            "sensor": ("1", "sensor"),
            "host": ("192.168.1.100", "connection"),
            "sweep_rate": ("10", "sensor"),
            "sweeps": ("-1", "sensor"),
            "gain": ("0.4", "sensor"),
            "range_start": ("0.18", "sensor"),
            "range_end": ("0.72", "sensor"),
            "sweep_buffer": ("100", "scan"),
            "power_bins": ("6", "sensor"),
            "subsweeps": ("16", "sensor"),
        }

        self.textboxes = {}
        for key, (text, _) in textbox_info.items():
            self.textboxes[key] = QLineEdit(self)
            self.textboxes[key].setText(text)
            self.textboxes[key].editingFinished.connect(self.check_values)

        self.textboxes["power_bins"].setVisible(False)
        self.textboxes["subsweeps"].setVisible(False)

    def init_checkboxes(self):
        # text, status, visible, enabled, function
        checkbox_info = {
            "clutter_file": ("", False, False, True, self.update_scan),
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
        self.service_props = {
            "Select service": [None, None],
            "IQ": [iq, iq.IQProcessor],
            "Envelope": [env, env.EnvelopeProcessor],
            "Sparse": [data_processing.get_sparse_processing_config(), None],
            "Power bin": [None, None],
            "Presence detection (IQ)": [prd, prd.PresenceDetectionProcessor],
            "Presence detection (sparse)": [psd, psd.PresenceDetectionSparseProcessor],
            "Breathing": [br, br.BreathingProcessor],
            "Phase tracking": [pht, pht.PhaseTrackingProcessor],
            "Sleep breathing": [sb, sb.PresenceDetectionProcessor],
            "Obstacle detection": [od, od.ObstacleDetectionProcessor],
        }

        self.external = self.service_props[self.current_module_label][1]

        module_processing_prop = self.service_props[self.current_module_label][0]
        if self.external:
            processing_config = module_processing_prop.get_processing_config()
        else:
            processing_config = module_processing_prop

        canvas = None

        mode_is_sparse = (self.current_mode == "sparse")
        self.textboxes["subsweeps"].setVisible(mode_is_sparse)
        self.labels["subsweeps"].setVisible(mode_is_sparse)
        mode_is_power_bin = (self.current_mode == "power_bin")
        self.textboxes["power_bins"].setVisible(mode_is_power_bin)
        self.labels["power_bins"].setVisible(mode_is_power_bin)
        self.env_profiles_dd.setVisible(self.current_mode == "envelope")

        self.cl_supported = False
        if self.current_module_label in ["IQ", "Envelope"]:
            self.cl_supported = True
        else:
            self.load_clutter_file(force_unload=True)

        self.buttons["create_cl"].setVisible(self.cl_supported)
        self.buttons["load_cl"].setVisible(self.cl_supported)
        self.buttons["load_cl"].setEnabled(self.cl_supported)
        self.labels["clutter"].setVisible(self.cl_supported)

        if self.current_module_label == "Select service":
            canvas = Label(self.acc_file)
            self.buttons["sensor_defaults"].setEnabled(False)
            return canvas
        else:
            self.buttons["sensor_defaults"].setEnabled(True)

        canvas = pg.GraphicsLayoutWidget()

        if not refresh:
            for m in self.service_labels:
                for key in self.service_labels[m]:
                    for element in self.service_labels[m][key]:
                        if "label" in element or "box" in element:
                            self.service_labels[m][key][element].setVisible(False)
        if not processing_config:
            self.service_params = None
            self.service_defaults = None
            self.service_section.hide()
        else:
            if not refresh:
                self.service_params = None
                self.service_defaults = None
                try:
                    self.service_params = processing_config
                    self.service_defaults = copy.deepcopy(self.service_params)
                except Exception:
                    pass
                self.add_params(self.service_params)
            if self.service_params:
                self.service_section.show()
            else:
                self.service_section.hide()

        if self.external:
            self.service_widget = self.service_props[self.current_module_label][0].PGUpdater(
                self.update_sensor_config(refresh=refresh), self.update_service_params())
            self.service_widget.setup(canvas)
            return canvas
        elif "power" in self.current_module_label.lower():
            self.power_plot_window = canvas.addPlot(row=0, col=0, title="Power bin")
            self.power_plot_window.showGrid(x=True, y=True)
            self.power_plot = pg.BarGraphItem(x=[],
                                              height=[],
                                              width=0.5,
                                              brush=pg.mkBrush(example_utils.color_cycler()),
                                              name="Power bins")
            self.power_plot_window.setLabel("left", "Amplitude")
            self.power_plot_window.setLabel("bottom", "Distance (mm)")
            self.power_plot_window.addItem(self.power_plot)
            self.textboxes["power_bins"].setVisible(True)
            self.labels["power_bins"].setVisible(True)
        elif "sparse" in self.current_module_label.lower():
            self.sparse_plot_window = canvas.addPlot(row=0, col=0, title="Sparse data")
            self.sparse_plot_window.showGrid(x=True, y=True)
            self.sparse_plot_window.setLabel("bottom", "Distance (mm)")
            self.sparse_plot_window.setLabel("left", "Amplitude")
            self.sparse_plot_window.setYRange(-2**15, 2**15)
            self.sparse_plot = pg.ScatterPlotItem(size=10)
            self.sparse_plot_window.addItem(self.sparse_plot)

            self.hist_move_image = canvas.addPlot(row=2, col=0, title="Movement history")
            self.hist_move = pg.ImageItem(autoDownsample=True)
            self.hist_move.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
            self.hist_move_image.addItem(self.hist_move)
            self.hist_move_image.setLabel("left", "Distance (mm)")
            self.hist_move_image.setLabel("bottom", "Time (s)")

            canvas.nextRow()

        if self.current_module_label.lower() == "sparse":
            row = 1
            title = "Amplitude history"
            basic_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
            colormap = LinearSegmentedColormap.from_list("mycmap", basic_cols)
            colormap._init()
            lut = (colormap._lut * 255).view(np.ndarray)

            self.hist_plot_image = canvas.addPlot(row=row, col=0, title=title)
            self.hist_plot = pg.ImageItem()
            self.hist_plot.setAutoDownsample(True)

            self.hist_plot.setLookupTable(lut)
            self.hist_plot_image.addItem(self.hist_plot)
            self.hist_plot_image.setLabel("left", "Distance (mm)")
            self.hist_plot_image.setLabel("bottom", "Time (s)")

        return canvas

    def init_dropdowns(self):
        # text, mode, config, external
        mode_info = [
            ("Select service", "", configs.EnvelopeServiceConfig, ""),
            ("IQ", "iq_data", configs.IQServiceConfig, "internal"),
            ("Envelope", "envelope_data", configs.EnvelopeServiceConfig, "internal"),
            ("Power bin", "power_bin", configs.PowerBinServiceConfig, "internal_power"),
            ("Sparse", "sparse_data", configs.SparseServiceConfig, "internal_sparse"),
            ("Breathing", "iq_data", br.get_sensor_config, "external"),
            ("Phase tracking", "iq_data", pht.get_sensor_config, "external"),
            ("Presence detection (IQ)", "iq_data", prd.get_sensor_config, "external"),
            ("Presence detection (sparse)", "sparse_data", psd.get_sensor_config, "external"),
            ("Sleep breathing", "iq_data", sb.get_sensor_config, "external"),
            ("Obstacle detection", "iq_data", od.get_sensor_config, "external"),
        ]

        self.mode_to_config = {text: [config(), ext] for text, _, config, ext in mode_info}
        self.mode_to_config_class = {text: config for text, _, config, _ in mode_info}

        self.module_dd = QComboBox(self)

        for text, *_ in mode_info:
            self.module_dd.addItem(text)

        self.module_dd.currentIndexChanged.connect(self.update_canvas)

        self.interface_dd = QComboBox(self)
        self.interface_dd.addItem("Socket")
        self.interface_dd.addItem("Serial")
        self.interface_dd.addItem("SPI")
        self.interface_dd.currentIndexChanged.connect(self.update_interface)

        self.ports_dd = QComboBox(self)
        self.ports_dd.hide()
        self.update_ports()

        self.env_profiles_dd = QComboBox(self)
        self.env_profiles_dd.addItem("Max SNR")
        self.env_profiles_dd.addItem("Max depth resolution")
        self.env_profiles_dd.addItem("Direct leakage")
        self.env_profiles_dd.currentIndexChanged.connect(self.set_profile)

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

    def set_profile(self):
        profile = self.env_profiles_dd.currentText().lower()

        if "snr" in profile:
            self.textboxes["gain"].setText(str(0.45))
        elif "depth" in profile:
            self.textboxes["gain"].setText(str(0.8))
        elif "leakage" in profile:
            self.textboxes["gain"].setText(str(0.2))
            self.textboxes["range_start"].setText(str(0))
            self.textboxes["range_end"].setText(str(0.3))

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
        input_dialog = QtWidgets.QInputDialog(self)
        input_dialog.setInputMode(QtWidgets.QInputDialog.IntInput)
        input_dialog.setFixedSize(400, 200)
        input_dialog.setCancelButtonText("Default")
        input_dialog.setIntRange(0, 3e6)
        input_dialog.setIntValue(self.baudrate)
        input_dialog.setOption(QtWidgets.QInputDialog.UsePlainTextEditForTextInput)
        input_dialog.setWindowTitle("Set baudrate")
        input_dialog.setLabelText(
                "Default is {}, only change if using special hardware"
                .format(self.DEFAULT_BAUDRATE)
                )

        if input_dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.baudrate = int(input_dialog.intValue())
        else:
            self.baudrate = self.DEFAULT_BAUDRATE
        input_dialog.deleteLater()

    def init_buttons(self):
        # key: text, function, enabled, hidden, group
        button_info = {
            "start": ("Start", self.start_scan, False, False, "scan"),
            "connect": ("Connect", self.connect_to_server, True, False, "connection"),
            "stop": ("Stop", self.stop_scan, False, False, "scan"),
            "create_cl": (
                "Scan Background",
                lambda: self.start_scan(create_cl=True),
                False,
                False,
                "scan",
            ),
            "load_cl": ("Load Background", self.load_clutter_file, False, False, "scan"),
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
        self.panel_sublayout = QtWidgets.QVBoxLayout()
        self.panel_sublayout.setContentsMargins(0, 3, 0, 3)
        self.panel_sublayout.setSpacing(0)

        server_section = CollapsibleSection("Connection", is_top=True)
        self.panel_sublayout.addWidget(server_section)
        server_section.grid.addWidget(self.labels["interface"], 0, 0)
        server_section.grid.addWidget(self.interface_dd, 0, 1)
        server_section.grid.addWidget(self.ports_dd, 1, 0)
        server_section.grid.addWidget(self.textboxes["host"], 1, 0, 1, 2)
        server_section.grid.addWidget(self.buttons["scan_ports"], 1, 1)
        server_section.grid.addWidget(self.buttons["advanced_port"], 2, 0, 1, 2)
        server_section.grid.addWidget(self.buttons["connect"], 3, 0, 1, 2)

        control_section = CollapsibleSection("Scan controls")
        self.panel_sublayout.addWidget(control_section)
        self.num = 0
        control_section.grid.addWidget(self.module_dd, self.increment(), 0, 1, 2)
        control_section.grid.addWidget(self.buttons["start"], self.increment(), 0)
        control_section.grid.addWidget(self.buttons["stop"], self.num, 1)
        control_section.grid.addWidget(self.buttons["save_scan"], self.increment(), 0)
        control_section.grid.addWidget(self.buttons["load_scan"], self.num, 1)
        control_section.grid.addWidget(
            self.buttons["replay_buffered"], self.increment(), 0, 1, 2)
        control_section.grid.addWidget(self.labels["sweep_buffer"], self.increment(), 0)
        control_section.grid.addWidget(self.textboxes["sweep_buffer"], self.num, 1)
        control_section.grid.addWidget(self.labels["empty_02"], self.increment(), 0)
        control_section.grid.addWidget(self.labels["clutter_status"], self.increment(), 0, 1, 2)
        control_section.grid.addWidget(self.labels["clutter"], self.increment(), 0)
        control_section.grid.addWidget(self.buttons["create_cl"], self.increment(), 0)
        control_section.grid.addWidget(self.buttons["load_cl"], self.num, 1)
        control_section.grid.addWidget(
            self.checkboxes["clutter_file"], self.increment(), 0, 1, 2)

        self.settings_section = CollapsibleSection("Sensor settings")
        self.panel_sublayout.addWidget(self.settings_section)
        self.num = 0
        self.settings_section.grid.addWidget(self.buttons["sensor_defaults"], self.num, 0, 1, 2)
        self.settings_section.grid.addWidget(self.labels["sensor"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["sensor"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["range_start"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.labels["range_end"], self.num, 1)
        self.settings_section.grid.addWidget(self.textboxes["range_start"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["range_end"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["sweep_rate"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["sweep_rate"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["gain"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["gain"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["sweeps"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["sweeps"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["power_bins"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["power_bins"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["subsweeps"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["subsweeps"], self.num, 1)
        self.settings_section.grid.addWidget(self.env_profiles_dd, self.increment(), 0, 1, 2)
        self.settings_section.grid.addWidget(self.labels["stitching"], self.increment(), 0, 1, 2)

        self.service_section = CollapsibleSection("Processing settings")
        self.panel_sublayout.addWidget(self.service_section)
        self.service_section.grid.addWidget(self.buttons["service_defaults"], 0, 0, 1, 2)
        self.serviceparams_sublayout_grid = self.service_section.grid

        self.advanced_section = CollapsibleSection("Advanced settings", init_collapsed=True)
        self.panel_sublayout.addWidget(self.advanced_section)
        self.advanced_section.grid.addWidget(self.buttons["advanced_defaults"], 0, 0, 1, 2)
        self.advanced_section.grid.addWidget(self.buttons["load_process_data"], 1, 0)
        self.advanced_section.grid.addWidget(self.buttons["save_process_data"], 1, 1)
        self.advanced_params_layout_grid = self.advanced_section.grid

        self.panel_sublayout.addStretch()

        self.service_section.hide()
        self.advanced_section.hide()

    def init_panel_scroll_area(self):
        self.panel_scroll_area = QtWidgets.QScrollArea()
        self.panel_scroll_area.setFrameShape(QFrame.NoFrame)
        self.panel_scroll_area.setMinimumWidth(350)
        self.panel_scroll_area.setMaximumWidth(600)
        self.panel_scroll_area.setWidgetResizable(True)
        self.panel_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.panel_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.panel_scroll_area.horizontalScrollBar().setEnabled(False)
        panel_scroll_area_widget = QWidget(self.panel_scroll_area)
        self.panel_scroll_area.setWidget(panel_scroll_area_widget)
        panel_scroll_area_widget.setLayout(self.panel_sublayout)

    def init_statusbar(self):
        self.statusBar().showMessage("Not connected")
        self.labels["sweep_info"].setFixedWidth(220)
        self.statusBar().addPermanentWidget(self.labels["saturated"])
        self.statusBar().addPermanentWidget(self.labels["sweep_info"])
        self.statusBar().addPermanentWidget(self.checkboxes["verbose"])
        self.statusBar().addPermanentWidget(self.checkboxes["opengl"])
        self.statusBar().setStyleSheet("QStatusBar{border-top: 1px solid lightgrey;}")
        self.statusBar().show()

    def add_params(self, params, start_up_mode=None):
        self.buttons["load_process_data"].hide()
        self.buttons["save_process_data"].hide()
        for mode in self.service_labels:
            for param_key in self.service_labels[mode]:
                for element in self.service_labels[mode][param_key]:
                    if element in ["label", "box", "button"]:
                        self.service_labels[mode][param_key][element].setVisible(False)

        if start_up_mode is None:
            mode = self.current_module_label
            set_visible = True
        else:
            mode = start_up_mode
            set_visible = False

        if not hasattr(self, "param_index"):
            self.param_index = 2

        if mode not in self.service_labels:
            self.service_labels[mode] = {}

        advanced_available = False
        for param_key, param_dict in params.items():
            if param_key not in self.service_labels[mode]:
                param_gui_dict = {}
                self.service_labels[mode][param_key] = param_gui_dict

                advanced_available = bool(param_dict.get("advanced"))
                if advanced_available:
                    grid = self.advanced_params_layout_grid
                else:
                    grid = self.serviceparams_sublayout_grid

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
                    grid.addWidget(param_gui_dict["checkbox"], self.param_index, 0, 1, 2)
                elif param_dict["value"] is not None:
                    param_gui_dict["label"] = QLabel(self)
                    param_gui_dict["label"].setMinimumWidth(125)
                    param_gui_dict["label"].setText(param_dict["name"])
                    param_gui_dict["box"] = QLineEdit(self)
                    param_gui_dict["box"].setText(str(param_dict["value"]))
                    param_gui_dict["limits"] = param_dict["limits"]
                    param_gui_dict["default"] = param_dict["value"]
                    grid.addWidget(param_gui_dict["label"], self.param_index, 0)
                    grid.addWidget(param_gui_dict["box"], self.param_index, 1)
                    param_gui_dict["box"].setVisible(set_visible)
                else:  # param is only a label
                    param_gui_dict["label"] = QLabel(self)
                    param_gui_dict["label"].setText(str(param_dict["text"]))
                    grid.addWidget(param_gui_dict["label"], self.param_index, 0, 1, 2)

                self.param_index += 1
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
            if advanced_available:
                self.advanced_section.show()
                self.advanced_section.button_event(override=True)
            else:
                self.advanced_section.hide()

    def sensor_defaults_handler(self):
        self.sweep_count = -1
        self.textboxes["sweeps"].setText("-1")

        self.env_profiles_dd.setCurrentIndex(0)

        config_class = self.mode_to_config_class[self.current_module_label]
        default_config = None if config_class is None else config_class()

        if default_config is None:
            return

        d = {
            "range_start": (0.18, ".2f"),
            "range_end": (0.60, ".2f"),
            "gain": (0.6, ".2f"),
            "sweep_rate": (40, "d"),
        }

        for key, (alt, fmt) in d.items():
            config_val = getattr(default_config, key)
            val = alt if config_val is None else config_val
            text = "{{:{}}}".format(fmt).format(val)
            self.textboxes[key].setText(text)

    def service_defaults_handler(self):
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

        self.current_mode = self.mode_to_config[self.current_module_label][0].mode

        if switching_module:
            self.data = None
            self.buttons["replay_buffered"].setEnabled(False)

        if force_update or switching_module:
            if self.canvas is not None:
                self.canvas_layout.removeWidget(self.canvas)
                self.canvas.setParent(None)
                self.canvas.deleteLater()

            if not switching_module:
                self.update_service_params()

            self.canvas = self.init_graphs(refresh=(not switching_module))
            self.canvas_layout.addWidget(self.canvas)

        if "select service" not in self.current_module_label.lower():
            self.update_sensor_config()

    def update_interface(self):
        if self.buttons["connect"].text() == "Disconnect":
            self.connect_to_server()

        if "serial" in self.interface_dd.currentText().lower():
            self.ports_dd.show()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].show()
            self.buttons["scan_ports"].show()
        elif "spi" in self.interface_dd.currentText().lower():
            self.ports_dd.hide()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()
        else:  # socket
            self.ports_dd.hide()
            self.textboxes["host"].show()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()

    def error_message(self, error):
        em = QtWidgets.QErrorMessage(self.main_widget)
        em.setWindowTitle("Error")
        em.showMessage(error)

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

    def start_scan(self, create_cl=False, from_file=False):
        if "Select" in self.current_module_label:
            self.error_message("Please select a service")
            return

        data_source = "stream"
        if from_file:
            try:
                sensor_config = self.data[0]["sensor_config"]
                self.update_settings(sensor_config)
            except Exception:
                print("Warning, could not restore config from cached data!")
                pass
            data_source = "file"
        self.sweep_buffer = 500

        if self.external:
            self.update_canvas(force_update=True)

        try:
            self.sweep_buffer = int(self.textboxes["sweep_buffer"].text())
        except Exception:
            self.error_message("Sweep buffer needs to be a positive integer\n")
            self.textboxes["sweep_buffer"].setText("500")

        if create_cl:
            self.sweep_buffer = min(self.sweep_buffer, self.max_cl_sweeps)
            self.creating_cl = True
            self.labels["empty_02"].hide()
            self.labels["clutter_status"].show()
            if self.cl_file:
                self.load_clutter_file(force_unload=True)
        else:
            self.creating_cl = False

        use_cl = False
        if self.checkboxes["clutter_file"].isChecked():
            use_cl = True

        processing_config = self.update_service_params()
        mode = self.current_module_label
        if mode == "Envelope" or mode == "IQ":
            processing_config = copy.deepcopy(self.update_service_params())
            processing_config["clutter_file"] = self.cl_file
            processing_config["use_clutter"] = use_cl
            processing_config["create_clutter"] = create_cl
            processing_config["sweeps_requested"] = self.sweep_count

        params = {
            "sensor_config": self.update_sensor_config(),
            "clutter_file": self.cl_file,
            "use_clutter": use_cl,
            "create_clutter": create_cl,
            "data_source": data_source,
            "service_type": self.current_module_label,
            "sweep_buffer": self.sweep_buffer,
            "service_params": processing_config,
        }

        self.threaded_scan = Threaded_Scan(params, parent=self)
        self.threaded_scan.sig_scan.connect(self.thread_receive)
        self.sig_scan.connect(self.threaded_scan.receive)

        self.buttons["start"].setEnabled(False)
        self.buttons["load_scan"].setEnabled(False)
        self.buttons["save_scan"].setEnabled(False)
        self.buttons["create_cl"].setEnabled(False)
        self.buttons["load_cl"].setEnabled(False)
        self.module_dd.setEnabled(False)
        self.buttons["stop"].setEnabled(True)
        self.checkboxes["opengl"].setEnabled(False)

        self.sweep_number = 0
        self.sweeps_skipped = 0
        self.threaded_scan.start()

        self.service_section.body_widget.setEnabled(False)
        self.settings_section.body_widget.setEnabled(False)
        self.buttons["connect"].setEnabled(False)
        self.buttons["replay_buffered"].setEnabled(False)

    def update_scan(self):
        if self.cl_file:
            clutter_file = self.cl_file
            if not self.checkboxes["clutter_file"].isChecked():
                clutter_file = None
            self.sig_scan.emit("set_clutter_flag", "", clutter_file)

    def stop_scan(self):
        self.sig_scan.emit("stop", "", None)
        self.buttons["load_scan"].setEnabled(True)
        self.buttons["load_cl"].setEnabled(self.cl_supported)
        self.buttons["create_cl"].setEnabled(self.cl_supported)
        self.labels["empty_02"].show()
        self.labels["clutter_status"].hide()
        self.module_dd.setEnabled(True)
        self.buttons["stop"].setEnabled(False)
        self.buttons["connect"].setEnabled(True)
        self.buttons["start"].setEnabled(True)
        self.service_section.body_widget.setEnabled(True)
        self.settings_section.body_widget.setEnabled(True)
        self.checkboxes["opengl"].setEnabled(True)
        if self.data is not None:
            self.buttons["replay_buffered"].setEnabled(True)
            self.buttons["save_scan"].setEnabled(True)

    def set_log_level(self):
        log_level = logging.INFO
        if self.checkboxes["verbose"].isChecked():
            log_level = logging.DEBUG
        example_utils.set_loglevel(log_level)

    def connect_to_server(self):
        if self.buttons["connect"].text() == "Connect":
            max_num = 4
            if "Select service" in self.current_module_label:
                self.module_dd.setCurrentIndex(2)

            if self.interface_dd.currentText().lower() == "socket":
                host = self.textboxes["host"].text()
                self.client = JSONClient(host)
                statusbar_connection_info = "socket ({})".format(host)
            elif self.interface_dd.currentText().lower() == "spi":
                self.client = RegSPIClient()
                statusbar_connection_info = "SPI"
            else:
                port = self.ports_dd.currentText()
                if "scan" in port.lower():
                    self.error_message("Please select port first!")
                    return
                if self.baudrate != self.DEFAULT_BAUDRATE:
                    print("Warning: Using non-standard baudrate of {}!".format(self.baudrate))
                self.client = RegClient(port, conf_baudrate=self.baudrate)
                max_num = 1
                statusbar_connection_info = "UART ({})".format(port)

            conf = self.update_sensor_config()
            sensor = 1
            connection_success = False
            error = None
            while sensor <= max_num:
                conf.sensor = sensor
                try:
                    self.client.setup_session(conf)
                    self.client.start_streaming()
                    self.client.stop_streaming()
                    connection_success = True
                    self.textboxes["sensor"].setText("{:d}".format(sensor))
                    break
                except Exception as e:
                    sensor += 1
                    error = e
            if connection_success:
                self.buttons["start"].setEnabled(True)
                self.buttons["create_cl"].setEnabled(self.cl_supported)
                self.buttons["load_cl"].setEnabled(self.cl_supported)
            else:
                self.error_message("Could not connect to server!\n{}".format(error))
                return

            self.buttons["connect"].setText("Disconnect")
            self.buttons["connect"].setStyleSheet("QPushButton {color: red}")
            self.buttons["advanced_port"].setEnabled(False)
            self.statusBar().showMessage("Connected via {}".format(statusbar_connection_info))
        else:
            self.buttons["connect"].setText("Connect")
            self.buttons["connect"].setStyleSheet("QPushButton {color: black}")
            self.sig_scan.emit("stop", "", None)
            self.buttons["start"].setEnabled(False)
            self.buttons["create_cl"].setEnabled(False)
            self.buttons["advanced_port"].setEnabled(True)
            self.statusBar().showMessage("Not connected")
            if self.cl_supported:
                self.buttons["load_cl"].setEnabled(True)

            try:
                self.client.stop_streaming()
            except Exception:
                pass

            try:
                self.client.disconnect()
            except Exception:
                pass

    def update_sensor_config(self, refresh=False):
        mode = self.current_module_label
        conf, service = self.mode_to_config[mode]

        if not conf:
            return None

        external = ("internal" not in service.lower())

        conf.sensor = int(self.textboxes["sensor"].text())
        if not refresh and external:
            self.textboxes["range_start"].setText("{:.2f}".format(conf.range_interval[0]))
            self.textboxes["range_end"].setText("{:.2f}".format(conf.range_interval[1]))
            self.textboxes["gain"].setText("{:.2f}".format(conf.gain))
            self.textboxes["sweep_rate"].setText("{:d}".format(conf.sweep_rate))
            self.sweep_count = -1
        else:
            stitching = self.check_values()
            conf.experimental_stitching = stitching
            conf.range_interval = [
                    float(self.textboxes["range_start"].text()),
                    float(self.textboxes["range_end"].text()),
            ]
            conf.sweep_rate = int(self.textboxes["sweep_rate"].text())
            conf.gain = float(self.textboxes["gain"].text())
            self.sweep_count = int(self.textboxes["sweeps"].text())
            if "power" in mode.lower():
                conf.bin_count = int(self.textboxes["power_bins"].text())
            if "sparse" in mode.lower():
                conf.number_of_subsweeps = int(self.textboxes["subsweeps"].text())
            if "envelope" in mode.lower():
                profile_text = self.env_profiles_dd.currentText().lower()
                if "snr" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.MAX_SNR
                elif "depth" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.MAX_DEPTH_RESOLUTION
                elif "leakage" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.DIRECT_LEAKAGE

        return conf

    def update_service_params(self):
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

        if len(errors):
            self.error_message("".join(errors))

        return self.service_params

    def check_values(self):
        mode = self.current_mode

        errors = []
        if not self.textboxes["sweep_rate"].text().isdigit():
            errors.append("Frequency must be an integer and not less than 0!\n")
            self.textboxes["sweep_rate"].setText("10")

        if not self.textboxes["sensor"].text().isdigit():
            errors.append("Sensor must be an integer between 1 and 4!\n")
            self.textboxes["sensor"].setText("0")
        else:
            sensor = int(self.textboxes["sensor"].text())
            sensor, e = self.check_limit(sensor, self.textboxes["sensor"], 1, 4)
            if e:
                errors.append("Sensor must be an integer between 1 and 4!\n")

        sweeps = self.is_float(self.textboxes["sweeps"].text(), is_positive=False)
        if sweeps == -1:
            pass
        elif sweeps >= 1:
            if not self.textboxes["sweeps"].text().isdigit():
                errors.append("Sweeps must be a -1 or an int larger than 0!\n")
                self.textboxes["sensor"].setText("-1")
        else:
            errors.append("Sweeps must be -1 or an int larger than 0!\n")
            self.textboxes["sweeps"].setText("-1")

        if "sparse" in mode.lower():
            e = False
            if not self.textboxes["subsweeps"].text().isdigit():
                self.textboxes["subsweeps"].setText("16")
                e = True
            else:
                subs = int(self.textboxes["subsweeps"].text())
                subs, e = self.check_limit(subs, self.textboxes["subsweeps"], 1, 16, set_to=16)
            if e:
                errors.append("Number of Subsweeps must be an int and between 1 and 16 !\n")

        gain = self.is_float(self.textboxes["gain"].text())
        gain, e = self.check_limit(gain, self.textboxes["gain"], 0, 1, set_to=0.7)
        if e:
            errors.append("Gain must be between 0 and 1!\n")

        min_start_range = 0 if "leakage" in self.env_profiles_dd.currentText().lower() else 0.06
        start = self.is_float(self.textboxes["range_start"].text(), is_positive=False)
        start, e = self.check_limit(start, self.textboxes["range_start"], min_start_range, 6.94)
        if e:
            errors.append("Start range must be between {}m and 6.94m!\n".format(min_start_range))

        end = self.is_float(self.textboxes["range_end"].text())
        end, e = self.check_limit(end, self.textboxes["range_end"], 0.12, 7)
        if e:
            errors.append("End range must be between 0.12m and 7.0m!\n")

        r = end - start

        env_max_range = 0.96
        iq_max_range = 0.72
        if self.current_mode in ["iq", "envelope"]:
            if self.interface_dd.currentText().lower() == "socket":
                env_max_range = 6.88
                iq_max_range = 6.88
            else:
                env_max_range = 5.0
                iq_max_range = 3.0

        stitching = False
        if r <= 0:
            errors.append("Range must not be less than 0!\n")
            self.textboxes["range_end"].setText(str(start + 0.06))
            end = start + 0.06
            r = end - start

        if self.current_mode == "envelope":
            if r > env_max_range:
                errors.append("Envelope range must be less than %.2fm!\n" % env_max_range)
                self.textboxes["range_end"].setText(str(start + env_max_range))
                end = start + env_max_range
                r = end - start
            elif r > 0.96:
                stitching = True

        if self.current_mode == "iq":
            if r > iq_max_range:
                errors.append("IQ range must be less than %.2fm!\n" % iq_max_range)
                self.textboxes["range_end"].setText(str(start + iq_max_range))
                end = start + iq_max_range
                r = end - start
            elif r > 0.72:
                stitching = True

        self.labels["stitching"].setVisible(stitching)
        self.textboxes["sweep_rate"].setEnabled(not stitching)

        if len(errors):
            self.error_message("".join(errors))

        return stitching

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

    def load_clutter_file(self, force_unload=False, fname=None):
        if not fname:
            if "unload" in self.buttons["load_cl"].text().lower() or force_unload:
                self.cl_file = None
                self.checkboxes["clutter_file"].setVisible(False)
                self.buttons["load_cl"].setText("Load Background")
                self.buttons["load_cl"].setStyleSheet("QPushButton {color: black}")
            else:
                options = QtWidgets.QFileDialog.Options()
                options |= QtWidgets.QFileDialog.DontUseNativeDialog
                fname, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self,
                    "Load background file",
                    "",
                    "NumPy data Files (*.npy)",
                    options=options
                    )

        if fname:
            self.cl_file = fname
            self.checkboxes["clutter_file"].setVisible(True)
            s = "Background: {}".format(ntpath.basename(fname))
            self.checkboxes["clutter_file"].setText(s)
            self.checkboxes["clutter_file"].setChecked(True)
            self.buttons["load_cl"].setText("Unload background")
            self.buttons["load_cl"].setStyleSheet("QPushButton {color: red}")

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
                "HDF5 data files (*.h5);; NumPy data files (*.npy)",
                options=options
                )

        if filename:
            cl_file = None
            if "h5" in filename:
                try:
                    f = h5py.File(filename, "r")
                except Exception as e:
                    self.error_message("{}".format(e))
                    print(e)
                    return

                try:
                    mode = f["service_type"][()]
                except Exception:
                    print("Service type not stored, setting to IQ!")
                    mode = "IQ"

                index = self.module_dd.findText(mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.module_dd.setCurrentIndex(index)

                try:
                    if "iq" in mode.lower():
                        conf = configs.IQServiceConfig()
                    elif "sparse" in mode.lower():
                        conf = configs.SparseServiceConfig()
                    else:
                        conf = configs.EnvelopeServiceConfig()
                    real = np.asarray(list(f["real"]))
                    im = np.asarray(list(f["imag"]))
                    sweeps = real[...] + 1j * im[...]
                    data_len = len(sweeps[:, 0])
                    length = range(len(sweeps))
                except Exception as e:
                    self.error_message("{}".format(e))
                    return

                try:
                    self.env_profiles_dd.setCurrentIndex(f["profile"][()])
                    mode = self.current_module_label
                    if self.service_params is not None:
                        if mode in self.service_labels:
                            for key in self.service_labels[mode]:
                                if "box" in self.service_labels[mode][key]:
                                    val = self.service_params[key]["type"](f[key][()])
                                    if self.service_params[key]["type"] == np.float:
                                        val = str("{:.4f}".format(val))
                                    else:
                                        val = str(val)
                                    self.service_labels[mode][key]["box"].setText(val)
                except Exception:
                    print("Could not restore processing parameters")
                    pass

                session_info = True
                try:
                    nr = np.asarray(list(f["sequence_number"]))
                    sat = np.asarray(list(f["data_saturated"]))
                except Exception:
                    session_info = False
                    print("Session info not stored!")

                try:
                    conf.sweep_rate = f["sweep_rate"][()]
                    conf.range_interval = [f["start"][()], f["end"][()]]
                    if "power" in mode:
                        conf.bin_count = int(self.textboxes["power_bins"].text())
                    if "sparse" in mode:
                        conf.number_of_subsweeps = int(self.textboxes["subsweeps"].text())
                    conf.gain = f["gain"][()]
                except Exception as e:
                    print("Config not stored in file...")
                    print(e)
                    conf.range_interval = [
                            float(self.textboxes["range_start"].text()),
                            float(self.textboxes["range_end"].text()),
                    ]
                    conf.sweep_rate = int(self.textboxes["sweep_rate"].text())

                cl_file = None
                try:
                    cl_file = f["clutter_file"][()]
                except Exception:
                    pass

                if session_info:
                    self.data = [
                        {
                            "sweep_data": sweeps[i],
                            "service_type": mode,
                            "sensor_config": conf,
                            "cl_file": cl_file,
                            "info": {
                                "sequence_number": nr[i],
                                "data_saturated": sat[i],
                            },
                        } for i in length]
                else:
                    self.data = [
                        {
                            "sweep_data": sweeps[i],
                            "service_type": mode,
                            "sensor_config": conf,
                            "cl_file": cl_file,
                        } for i in length]
            else:
                try:
                    data = np.load(filename, allow_pickle=True)
                    mode = data[0]["service_type"]
                    cl_file = data[0]["cl_file"]
                    data_len = len(data)
                    conf = data[0]["sensor_config"]
                except Exception as e:
                    self.error_message("{}".format(e))
                    return
                index = self.module_dd.findText(mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.module_dd.setCurrentIndex(index)
                self.data = data

            self.textboxes["range_start"].setText(str(conf.range_interval[0]))
            self.textboxes["range_end"].setText(str(conf.range_interval[1]))
            self.textboxes["gain"].setText(str(conf.gain))
            self.textboxes["sweep_rate"].setText(str(int(conf.sweep_rate)))
            if "power" in mode.lower():
                self.textboxes["power_bins"].setText(str(conf.bin_count))
            if "sparse" in mode.lower():
                self.textboxes["subsweeps"].setText(str(conf.number_of_subsweeps))

            if isinstance(cl_file, str) or isinstance(cl_file, os.PathLike):
                try:
                    os.path.isfile(cl_file)
                    self.load_clutter_file(fname=cl_file)
                except Exception as e:
                    print("Background file not found")
                    print(e)

            self.textboxes["sweep_buffer"].setText(str(data_len))
            self.start_scan(from_file=True)

    def save_scan(self, data, clutter=False):
        mode = self.current_module_label
        if "sleep" in mode.lower():
            if int(self.textboxes["sweep_buffer"].text()) < 1000:
                self.error_message("Please set sweep buffer to >= 1000")
                return
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.DontUseNativeDialog

        title = "Save scan"
        file_types = "HDF5 data files (*.h5);; NumPy data files (*.npy)"
        if clutter:
            title = "Save background"
            file_types = "NumPy data files (*.npy)"
        filename, info = QtWidgets.QFileDialog.getSaveFileName(
                self, title, "", file_types, options=options)

        if filename:
            if clutter:
                try:
                    np.save(filename, data)
                except Exception as e:
                    self.error_message("Failed to save file:\n {:s}".format(e))
                    return
                self.cl_file = filename
                if "npy" not in filename.lower():
                    self.cl_file += ".npy"
                label_text = "Background: {}".format(ntpath.basename(filename))
                self.checkboxes["clutter_file"].setText(label_text)
                self.checkboxes["clutter_file"].setChecked(True)
                self.checkboxes["clutter_file"].setVisible(True)
                self.buttons["load_cl"].setText("Unload background")
                self.buttons["load_cl"].setStyleSheet("QPushButton {color: red}")
            else:
                if "h5" in info:
                    sweep_data = []
                    info_available = True
                    saturated_available = True
                    try:
                        data[0]["info"]["sequence_number"]
                        sequence_number = []
                        data_saturated = []
                    except Exception as e:
                        print(e)
                        print("Cannot save session info!")
                        info_available = False

                    for sweep in data:
                        sweep_data.append(sweep["sweep_data"])
                        if info_available:
                            sequence_number.append(sweep["info"]["sequence_number"])
                            try:
                                data_saturated.append(sweep["info"]["data_saturated"])
                            except Exception:
                                data_saturated.append(False)
                                saturated_available = False
                    if not saturated_available:
                        print("Session info does not contain saturation data!")

                    sweep_data = np.asarray(sweep_data)
                    if info_available:
                        sequence_number = np.asarray(sequence_number)
                        data_saturated = np.asarray(data_saturated)
                    try:
                        sensor_config = data[0]["sensor_config"]
                    except Exception as e:
                        self.error_message("Cannot fetch sensor_config!\n {:s}".format(e))
                        return

                    if ".h5" not in filename:
                        filename = filename + ".h5"
                    try:
                        f = h5py.File(filename, "w")
                    except Exception as e:
                        self.error_message("Failed to save file:\n {:s}".format(e))
                        return
                    f.create_dataset("imag", data=np.imag(sweep_data), dtype=np.float32)
                    f.create_dataset("real", data=np.real(sweep_data), dtype=np.float32)
                    f.create_dataset("sweep_rate", data=int(self.textboxes["sweep_rate"].text()),
                                     dtype=np.float32)
                    f.create_dataset("start", data=float(sensor_config.range_start),
                                     dtype=np.float32)
                    f.create_dataset("end", data=float(sensor_config.range_end),
                                     dtype=np.float32)
                    f.create_dataset("gain", data=float(sensor_config.gain), dtype=np.float32)
                    f.create_dataset("service_type", data=mode.lower(),
                                     dtype=h5py.special_dtype(vlen=str))
                    f.create_dataset("clutter_file", data=self.cl_file,
                                     dtype=h5py.special_dtype(vlen=str))
                    f.create_dataset("profile", data=self.env_profiles_dd.currentIndex(),
                                     dtype=np.int)
                    if info_available:
                        f.create_dataset("sequence_number", data=sequence_number, dtype=np.int)
                        f.create_dataset("data_saturated", data=data_saturated, dtype='u1')
                    if "power_bins" in mode.lower():
                        f.create_dataset("power_bins", data=int(sensor_config.power_bins),
                                         dtype=np.int)
                    if "sparse" in mode.lower():
                        f.create_dataset("subsweeps", data=int(sensor_config.number_of_subsweeps),
                                         dtype=np.int)
                    if mode in self.service_labels:
                        for key in self.service_params:
                            f.create_dataset(key, data=self.service_params[key]["value"],
                                             dtype=np.float32)
                else:
                    try:
                        data[0]["service_params"] = self.service_params
                    except Exception:
                        pass
                    try:
                        np.save(filename, data)
                    except Exception as e:
                        self.error_message("Failed to save file:\n {:s}".format(e))
                        return

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
            self.error_message("{}".format(message))
            if "client" in message_type:
                self.stop_scan()
                if self.buttons["connect"].text() == "Disconnect":
                    self.connect_to_server()
                self.buttons["create_cl"].setEnabled(False)
                self.buttons["start"].setEnabled(False)
            if "clutter" in message_type:
                self.load_clutter_file(force_unload=True)
        elif message_type == "clutter_data":
            self.save_scan(data, clutter=True)
        elif message_type == "scan_data":
            self.data = data
        elif message_type == "scan_done":
            self.stop_scan()
            if "Connect" == self.buttons["connect"].text():
                self.buttons["start"].setEnabled(False)
        elif "update_power_plots" in message_type:
            if data:
                self.update_power_plots(data)
        elif "update_external_plots" in message_type:
            if data:
                self.update_external_plots(data)
        elif "update_sparse_plots" in message_type:
            if data:
                self.update_sparse_plots(data)
        elif "sweep_info" in message_type:
            self.update_sweep_info(data)
        elif "session_info" in message_type:
            self.update_ranges(data)
        elif "process_data" in message_type:
            self.advanced_process_data["process_data"] = data
        else:
            print("Thread data not implemented!")
            print(message_type, message, data)

    def update_power_plots(self, data):
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        if not data["sweep"]:
            bin_num = int(self.textboxes["power_bins"].text())
            bin_width = (xend - xstart)/(bin_num + 1)
            self.power_plot_window.setXRange(xstart, xend)
            self.power_plot.setOpts(x=data["x_mm"], width=bin_width)
            self.power_plot_window.setXRange(xstart - bin_width / 2,
                                             xend + bin_width / 2)
            self.smooth_power = example_utils.SmoothMax(
                int(self.textboxes["sweep_rate"].text()),
                tau_decay=1,
                tau_grow=0.2
                )
        self.power_plot.setOpts(height=data["iq_data"])
        self.power_plot_window.setYRange(0, self.smooth_power.update(np.max(data["iq_data"])))

    def update_sparse_plots(self, data):
        if not data["sweep"]:
            self.smooth_sparse = example_utils.SmoothMax(
                int(self.textboxes["sweep_rate"].text()),
                tau_decay=1,
                tau_grow=0.2
                )

            time_res = 1.0 / data["sensor_config"].sweep_rate

            depth_start = data["x_mm"][0]
            depth_end = data["x_mm"][-1]
            depth_length = depth_end - depth_start
            depth_size = data["hist_env"].shape[1]
            depth_res = depth_length / (depth_size - 1)

            for im in [self.hist_plot, self.hist_move]:
                im.resetTransform()
                im.translate(0, data["x_mm"][0] - depth_res / 2)
                im.scale(time_res, depth_res)

        self.sparse_plot.setData(data["x_mm"], data["iq_data"])
        m = self.smooth_sparse.update(max(500, np.max(np.abs(data["iq_data"]))))
        self.sparse_plot_window.setYRange(-m, m)

        self.hist_plot.updateImage(data["hist_env"], levels=(0, 256))
        move_max = max(np.max(data["hist_move"]) + 100, 1000)
        self.hist_move.updateImage(data["hist_move"], levels=(0, move_max))

    def update_external_plots(self, data):
        self.service_widget.update(data)

    def update_sweep_info(self, data):
        self.sweeps_skipped += data["sequence_number"] - (self.sweep_number + 1)
        self.sweep_number = data["sequence_number"]

        nr = ""
        if self.sweep_number > 1e6:
            self.sweep_number = 1e6
            nr = ">"

        skip = ""
        if self.sweeps_skipped > 1e6:
            self.sweeps_skipped = 1e6
            skip = ">"

        self.labels["sweep_info"].setText("Sweeps: {:s}{:d} (skipped {:s}{:d})".format(
            nr, self.sweep_number, skip, self.sweeps_skipped))

        if data.get("data_saturated"):
            self.labels["saturated"].setStyleSheet("color: red")
        else:
            self.labels["saturated"].setStyleSheet("color: #f0f0f0")

        if self.creating_cl:
            clutter_sweeps = min(self.max_cl_sweeps, self.sweep_buffer)
            sweeps = self.sweep_number - self.sweeps_skipped
            clutter_status = "Scanning background sweep {:d} of {:d}".format(sweeps,
                                                                             clutter_sweeps)
            self.labels["clutter_status"].setText(clutter_status)

    def update_ranges(self, data):
        old_start = float(self.textboxes["range_start"].text())
        old_end = float(self.textboxes["range_end"].text())
        start = data["actual_range_start"]
        self.textboxes["range_start"].setText("{:.2f}".format(start))
        end = start + data["actual_range_length"]
        self.textboxes["range_end"].setText("{:.2f}".format(end))
        print("Updated range settings to match session info!")
        print("Start {:.3f} -> {:.3f}".format(old_start, start))
        print("End   {:.3f} -> {:.3f}".format(old_end, end))

    def start_up(self):
        if os.path.isfile(self.last_file):
            try:
                last = np.load(self.last_file, allow_pickle=True)
                self.update_settings(last.item()["sensor_config"], last.item())
            except Exception as e:
                print("Could not load settings from last session\n{}".format(e))

    def update_settings(self, sensor_config, last_config=None):
        if last_config:
            # restore last sensor settings
            try:
                self.env_profiles_dd.setCurrentIndex(last_config["profile"])
                self.textboxes["sweep_buffer"].setText(last_config["sweep_buffer"])
                self.textboxes["sensor"].setText("{:d}".format(sensor_config.sensor[0]))
                self.interface_dd.setCurrentIndex(last_config["interface"])
                self.ports_dd.setCurrentIndex(last_config["port"])
                self.textboxes["host"].setText(last_config["host"])
                self.sweep_count = last_config["sweep_count"]
            except Exception as e:
                print("Warning, could not restore last session\n{}".format(e))
            # restore all service settings
            try:
                if last_config["service_settings"]:
                    for mode in last_config["service_settings"]:
                        external = self.service_props[mode][1]
                        if external:
                            processing_config = self.service_props[mode][0].get_processing_config()
                        else:
                            processing_config = self.service_props[mode][0]
                        self.add_params(processing_config, start_up_mode=mode)

                        labels = last_config["service_settings"][mode]
                        for key in labels:
                            if "checkbox" in labels[key]:
                                self.service_labels[mode][key]["checkbox"].setChecked(
                                    labels[key]["checkbox"])
                            elif "box" in labels[key]:
                                self.service_labels[mode][key]["box"].setText(
                                    str(labels[key]["box"]))
            except Exception as e:
                print("Warning, could not restore service settings\n{}".format(e))
            try:
                if last_config.get("baudrate") is not None:
                    self.baudrate = last_config["baudrate"]
            except Exception:
                print("Warning, could not restore baudrate for UART!")
                raise

        try:
            self.textboxes["gain"].setText("{:.1f}".format(sensor_config.gain))
            self.textboxes["sweep_rate"].setText(str(int(sensor_config.sweep_rate)))
            self.textboxes["range_start"].setText("{:.2f}".format(sensor_config.range_interval[0]))
            self.textboxes["range_end"].setText("{:.2f}".format(sensor_config.range_interval[1]))
            if hasattr(sensor_config, "bin_count"):
                self.textboxes["power_bins"].setText("{:d}".format(sensor_config.bin_count))
            if hasattr(sensor_config, "number_of_subsweeps"):
                subs = sensor_config.number_of_subsweeps
                self.textboxes["subsweeps"].setText("{:d}".format(subs))
        except Exception as e:
            print("Warning, could not update config settings\n{}".format(e))

    def increment(self):
        self.num += 1
        return self.num

    def closeEvent(self, event=None):
        if "select" not in str(self.current_module_label).lower():
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
            last_config = {
                "sensor_config": self.update_sensor_config(),
                "sweep_count": self.sweep_count,
                "host": self.textboxes["host"].text(),
                "sweep_buffer": self.textboxes["sweep_buffer"].text(),
                "interface": self.interface_dd.currentIndex(),
                "port": self.ports_dd.currentIndex(),
                "profile": self.env_profiles_dd.currentIndex(),
                "service_settings": service_params,
                "baudrate": self.baudrate,
                }

            np.save(self.last_file, last_config, allow_pickle=True)

        try:
            self.client.disconnect()
        except Exception:
            pass
        self.close()


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
        self.sweep_count = parent.sweep_count
        if self.sweep_count == -1:
            self.sweep_count = np.inf

        self.finished.connect(self.stop_thread)

    def stop_thread(self):
        self.quit()

    def run(self):
        if self.params["data_source"] == "stream":
            data = None

            try:
                session_info = self.client.setup_session(self.sensor_config)
                if not self.check_session_info(session_info):
                    self.emit("session_info", "", session_info)
                self.radar.prepare_processing(self, self.params)
                self.client.start_streaming()
            except Exception as e:
                self.emit("client_error", "Failed to setup streaming!\n"
                          "{}".format(self.format_error(e)))
                self.running = False

            try:
                while self.running:
                    info, sweep = self.client.get_next()
                    self.emit("sweep_info", "", info)
                    plot_data, data = self.radar.process(sweep, info)
                    if plot_data and plot_data["sweep"] + 1 >= self.sweep_count:
                        self.running = False
            except Exception as e:
                msg = "Failed to communicate with server!\n{}".format(self.format_error(e))
                self.emit("client_error", msg)

            try:
                self.client.stop_streaming()
            except Exception:
                pass

            if data:
                self.emit("scan_data", "", data)
        elif self.params["data_source"] == "file":
            self.radar.prepare_processing(self, self.params)
            self.radar.process_saved_data(self.data, self)
        else:
            self.emit("error", "Unknown mode %s!" % self.mode)
        self.emit("scan_done", "", "")

    def receive(self, message_type, message, data=None):
        if message_type == "stop" and self.running:
            self.running = False
            self.radar.abort_processing()
            if self.params["create_clutter"]:
                self.emit("error", "Background scan not finished. "
                          "Wait for sweep buffer to fill to finish background scan")
        elif message_type == "set_clutter_flag":
            self.radar.set_clutter_flag(data)

    def emit(self, message_type, message, data=None):
        self.sig_scan.emit(message_type, message, data)

    def format_error(self, e):
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        err = "{}\n{}\n{}\n{}".format(exc_type, fname, exc_tb.tb_lineno, e)
        return err

    def check_session_info(self, data):
        try:
            start = self.sensor_config.range_start
            length = self.sensor_config.range_length
            start_ok = abs(start - data["actual_range_start"]) < 0.01
            len_ok = abs(length - data["actual_range_length"]) < 0.01
        except (AttributeError, KeyError, TypeError):
            pass
        else:
            if not start_ok or not len_ok:
                self.sensor_config.range_start = data["actual_range_start"]
                self.sensor_config.range_length = data["actual_range_length"]
                return False
        return True


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
    example_utils.config_logging(level=logging.INFO)

    app = QApplication(sys.argv)
    ex = GUI()

    signal.signal(signal.SIGINT, lambda *_: sigint_handler(ex))

    # Makes sure the signal is caught
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(200)

    sys.exit(app.exec_())
