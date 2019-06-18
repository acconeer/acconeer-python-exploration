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
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtCore import pyqtSignal
from PyQt5 import QtCore, QtWidgets

from matplotlib.colors import LinearSegmentedColormap

import pyqtgraph as pg

from acconeer_utils.clients.reg.client import RegClient, RegSPIClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils

sys.path.append("")  # noqa: E402
import data_processing
from helper import Label, CollapsibleSection

sys.path.append(os.path.join(os.path.dirname(__file__), "../examples/processing"))  # noqa: E402
import presence_detection_iq as prd
import presence_detection_sparse as psd
import phase_tracking as pht
import breathing as br
import sleep_breathing as sb
import obstacle_detection as od


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
    env_plot_max_y = 0
    env_plot_min_y = 0
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
        self.setWindowIcon(QIcon(self.acc_file))

        self.init_labels()
        self.init_textboxes()
        self.init_buttons()
        self.init_dropdowns()
        self.init_checkboxes()
        self.init_sublayouts()
        self.init_panel_scroll_area()
        self.init_statusbar()

        self.main_widget = QWidget()
        self.main_layout = QtWidgets.QGridLayout(self.main_widget)

        self.canvas = self.init_graphs()
        self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.main_layout.addWidget(self.canvas, 0, 0)
        self.main_layout.addWidget(self.panel_scroll_area, 0, 1)

        self.main_layout.setColumnStretch(0, 1)

        self.main_widget.setLayout(self.main_layout)
        self.setCentralWidget(self.main_widget)

        self.setGeometry(50, 50, 1200, 800)
        self.setWindowTitle("Acconeer Exploration GUI")
        self.show()
        self.start_up()

        self.radar = data_processing.DataProcessing()

    def init_labels(self):
        # key: text, group
        label_info = {
            "sensor": ("Sensor", "sensor"),
            "gain": ("Gain", "sensor"),
            "frequency": ("Sweep frequency", "sensor"),
            "sweeps": ("Number of sweeps", "sensor"),
            "sweep_buffer": ("Sweep buffer", "scan"),
            "start_range": ("Start (m)", "sensor"),
            "end_range": ("Stop (m)", "sensor"),
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
            "frequency": ("10", "sensor"),
            "sweeps": ("-1", "sensor"),
            "gain": ("0.4", "sensor"),
            "start_range": ("0.18", "sensor"),
            "end_range": ("0.72", "sensor"),
            "sweep_buffer": ("100", "scan"),
            "power_bins": ("6", "sensor"),
            "subsweeps": ("16", "sensor"),
        }

        self.textboxes = {}
        for key, (text, _) in textbox_info.items():
            self.textboxes[key] = QLineEdit(self)
            self.textboxes[key].setText(text)
            self.textboxes[key].editingFinished.connect(
                lambda: self.check_values(self.mode_to_config[self.mode.currentText()][0].mode)
            )

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

    def init_graphs(self, mode="Select service", refresh=False):
        self.service_props = {
            "Select service": [None, None],
            "IQ": [data_processing.get_internal_processing_config(), None],
            "Envelope": [data_processing.get_internal_processing_config(), None],
            "Sparse": [data_processing.get_sparse_processing_config(), None],
            "Power bin": [None, None],
            "Presence detection (IQ)": [prd, prd.PresenceDetectionProcessor],
            "Presence detection (sparse)": [psd, psd.PresenceDetectionSparseProcessor],
            "Breathing": [br, br.BreathingProcessor],
            "Phase tracking": [pht, pht.PhaseTrackingProcessor],
            "Sleep breathing": [sb, sb.PresenceDetectionProcessor],
            "Obstacle detection": [od, od.ObstacleDetectionProcessor],
        }

        self.external = self.service_props[mode][1]
        if self.external:
            processing_config = self.service_props[mode][0].get_processing_config()
        else:
            processing_config = self.service_props[mode][0]

        canvas = None

        if "sparse" in mode.lower():
            self.textboxes["subsweeps"].setVisible(True)
            self.labels["subsweeps"].setVisible(True)
        else:
            self.textboxes["subsweeps"].setVisible(False)
            self.labels["subsweeps"].setVisible(False)
        self.textboxes["power_bins"].setVisible(False)
        self.labels["power_bins"].setVisible(False)
        self.profiles.setVisible(False)

        self.cl_supported = False
        if "IQ" in self.mode.currentText() or "Envelope" in self.mode.currentText():
            self.cl_supported = True
        else:
            self.load_clutter_file(force_unload=True)

        self.buttons["create_cl"].setVisible(self.cl_supported)
        self.buttons["load_cl"].setVisible(self.cl_supported)
        self.labels["clutter"].setVisible(self.cl_supported)

        self.current_canvas = mode

        font = QFont()
        font.setPixelSize(12)
        ax_color = (0, 0, 0)
        ax = ("bottom", "left")

        if mode == "Select service":
            canvas = Label(self.acc_file)
            self.buttons["sensor_defaults"].setEnabled(False)
            return canvas
        else:
            self.buttons["sensor_defaults"].setEnabled(True)

        pg.setConfigOption("background", "#f0f0f0")
        pg.setConfigOption("foreground", "k")
        pg.setConfigOption("leftButtonPan", False)
        pg.setConfigOptions(antialias=True)
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
            self.service_widget = self.service_props[mode][0].PGUpdater(
                self.update_sensor_config(refresh=refresh), self.update_service_params())
            self.service_widget.setup(canvas)
            return canvas
        elif "power" in mode.lower():
            self.power_plot_window = canvas.addPlot(row=0, col=0, title="Power bin")
            self.power_plot_window.showGrid(x=True, y=True)
            for i in ax:
                self.power_plot_window.getAxis(i).tickFont = font
                self.power_plot_window.getAxis(i).setPen(ax_color)
            pen = pg.mkPen(example_utils.color_cycler(0), width=2)
            self.power_plot = pg.BarGraphItem(x=np.arange(1, 7),
                                              height=np.linspace(0, 6, num=6),
                                              width=.5,
                                              pen=pen,
                                              name="Power bins")
            self.power_plot_window.setLabel("left", "Amplitude")
            self.power_plot_window.setLabel("bottom", "Power bin range (mm)")
            self.power_plot_window.setYRange(0, 10)
            self.power_plot_window.setXRange(0.5, 6.5)
            self.power_plot_window.addItem(self.power_plot)
            self.textboxes["power_bins"].setVisible(True)
            self.labels["power_bins"].setVisible(True)
        elif "sparse" in mode.lower():
            self.sparse_plot_window = canvas.addPlot(row=0, col=0, title="Sparse mode")
            self.sparse_plot_window.showGrid(x=True, y=True)
            self.sparse_plot_window.setLabel("bottom", "Depth (mm)")
            self.sparse_plot_window.setLabel("left", "Amplitude")
            self.sparse_plot_window.setYRange(-2**15, 2**15)
            self.sparse_plot = pg.ScatterPlotItem(size=10)
            self.sparse_plot_window.addItem(self.sparse_plot)
            for i in ax:
                self.sparse_plot_window.getAxis(i).tickFont = font
                self.sparse_plot_window.getAxis(i).setPen(ax_color)

            self.hist_move_image = canvas.addPlot(row=2, col=0, title="Movement history")
            self.hist_move = pg.ImageItem(autoDownsample=True)
            self.hist_move.setLookupTable(example_utils.pg_mpl_cmap("viridis"))
            pen = example_utils.pg_pen_cycler(1)
            self.hist_move_image.addItem(self.hist_move)
            self.hist_move_image.setLabel("left", "Distance (mm)")
            self.hist_move_image.setLabel("bottom", "Time (s)")

            canvas.nextRow()
        else:
            self.envelope_plot_window = canvas.addPlot(row=0, col=0, title="Envelope")
            self.envelope_plot_window.showGrid(x=True, y=True)
            self.envelope_plot_window.addLegend(offset=(-10, 10))
            for i in ax:
                self.envelope_plot_window.getAxis(i).tickFont = font
                self.envelope_plot_window.getAxis(i).setPen(ax_color)

            pen = example_utils.pg_pen_cycler()
            self.envelope_plot = self.envelope_plot_window.plot(range(10),
                                                                np.zeros(10),
                                                                pen=pen,
                                                                name="Envelope")
            self.envelope_plot_window.setYRange(0, 1)
            pen = pg.mkPen(0.2, width=2, style=QtCore.Qt.DotLine)
            self.clutter_plot = self.envelope_plot_window.plot(range(10),
                                                               np.zeros(10),
                                                               pen=pen,
                                                               name="Background")
            self.env_peak_vline = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(width=2,
                                                  style=QtCore.Qt.DotLine))
            self.envelope_plot_window.addItem(self.env_peak_vline)
            self.clutter_plot.setZValue(2)

            self.peak_text = pg.TextItem(text="", color=(1, 1, 1), anchor=(0, 1), fill="#f0f0f0")
            self.peak_text.setZValue(3)
            self.envelope_plot_window.addItem(self.peak_text)
            self.envelope_plot_window.setLabel("left", "Amplitude")
            self.envelope_plot_window.setLabel("bottom", "Distance (mm)")

            if mode.lower() == "iq":
                self.iq_plot_window = canvas.addPlot(row=1, col=0, title="Phase")
                self.iq_plot_window.showGrid(x=True, y=True)
                self.iq_plot_window.addLegend(offset=(-10, 10))
                for i in ax:
                    self.iq_plot_window.getAxis(i).tickFont = font
                    self.iq_plot_window.getAxis(i).setPen(ax_color)
                pen = example_utils.pg_pen_cycler()
                self.iq_plot = self.iq_plot_window.plot(range(10),
                                                        np.arange(10)*0,
                                                        pen=pen,
                                                        name="IQ Phase")
                self.iq_plot_window.setLabel("left", "Normalized phase")
                self.iq_plot_window.setLabel("bottom", "Distance (mm)")
                canvas.nextRow()
            else:
                self.profiles.setVisible(True)

        if mode.lower() in ["iq", "envelope", "sparse"]:
            row = 1
            title = "Envelope History"
            if "iq" in mode.lower():
                row = 2
            if "sparse" in mode.lower():
                title = "Sparse avg amplitude history"
                basic_cols = ["steelblue", "lightblue", "#f0f0f0", "moccasin", "darkorange"]
                colormap = LinearSegmentedColormap.from_list("mycmap", basic_cols)
                colormap._init()
                lut = (colormap._lut * 255).view(np.ndarray)
            else:
                lut = example_utils.pg_mpl_cmap("viridis")

            self.hist_plot_image = canvas.addPlot(row=row, col=0, title=title)
            self.hist_plot = pg.ImageItem()
            self.hist_plot.setAutoDownsample(True)

            self.hist_plot.setLookupTable(lut)
            pen = example_utils.pg_pen_cycler(1)
            self.hist_plot_image.addItem(self.hist_plot)
            self.hist_plot_image.setLabel("left", "Distance (mm)")
            self.hist_plot_image.setLabel("bottom", "Time (s)")
            for i in ax:
                self.hist_plot_image.getAxis(i).tickFont = font
                self.hist_plot_image.getAxis(i).setPen(ax_color)
        if mode.lower() in ["iq", "envelope"]:
            self.hist_plot_peak = self.hist_plot_image.plot(range(10),
                                                            np.zeros(10),
                                                            pen=pen)

        return canvas

    def init_dropdowns(self):
        # text, mode, config, external
        mode_info = [
            ("Select service", "", configs.EnvelopeServiceConfig(), ""),
            ("IQ", "iq_data", configs.IQServiceConfig(), "internal"),
            ("Envelope", "envelope_data", configs.EnvelopeServiceConfig(), "internal"),
            ("Power bin", "power_bin", configs.PowerBinServiceConfig(), "internal_power"),
            ("Sparse", "sparse_data", configs.SparseServiceConfig(), "internal_sparse"),
            ("Breathing", "iq_data", br.get_sensor_config(), "external"),
            ("Phase tracking", "iq_data", pht.get_sensor_config(), "external"),
            ("Presence detection (IQ)", "iq_data", prd.get_sensor_config(), "external"),
            ("Presence detection (sparse)", "sparse_data", psd.get_sensor_config(), "external"),
            ("Sleep breathing", "iq_data", sb.get_sensor_config(), "external"),
            ("Obstacle detection", "iq_data", od.get_sensor_config(), "external"),
        ]

        self.mode_to_param = {text: mode for text, mode, *_ in mode_info}
        self.mode_to_config = {text: [config, ext] for text, _, config, ext in mode_info}

        self.mode = QComboBox(self)
        self.mode.move(50, 250)

        self.conf_defaults = {}
        for text, mode, config, ext in mode_info:
            self.mode.addItem(text)

            if mode:
                self.conf_defaults[text] = {}
                if "external" in ext:
                    self.conf_defaults[text]["gain"] = config.gain
                    self.conf_defaults[text]["start_range"] = config.range_interval[0]
                    self.conf_defaults[text]["end_range"] = config.range_interval[1]
                    self.conf_defaults[text]["frequency"] = config.sweep_rate
                else:
                    self.conf_defaults[text]["start_range"] = 0.18
                    self.conf_defaults[text]["end_range"] = 0.60
                    self.conf_defaults[text]["gain"] = 0.7
                    self.conf_defaults[text]["frequency"] = 60

        self.mode.currentIndexChanged.connect(self.update_canvas)

        self.interface = QComboBox(self)
        self.interface.addItem("Socket")
        self.interface.addItem("Serial")
        self.interface.addItem("SPI")
        self.interface.currentIndexChanged.connect(self.update_interface)

        self.ports = QComboBox(self)
        self.ports.hide()
        self.update_ports()

        self.profiles = QComboBox(self)
        self.profiles.addItem("Max SNR")
        self.profiles.addItem("Max depth resolution")
        self.profiles.addItem("Direct leakage")
        self.profiles.currentIndexChanged.connect(self.set_profile)

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
        profile = self.profiles.currentText().lower()

        if "snr" in profile:
            self.textboxes["gain"].setText(str(0.45))
        elif "depth" in profile:
            self.textboxes["gain"].setText(str(0.8))
        elif "leakage" in profile:
            self.textboxes["gain"].setText(str(0.2))
            self.textboxes["start_range"].setText(str(0))
            self.textboxes["end_range"].setText(str(0.3))

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

        self.ports.clear()
        self.ports.addItems(ports)

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

        server_section = CollapsibleSection("Connection")
        self.panel_sublayout.addWidget(server_section)
        server_section.grid.addWidget(self.labels["interface"], 0, 0)
        server_section.grid.addWidget(self.interface, 0, 1)
        server_section.grid.addWidget(self.ports, 1, 0)
        server_section.grid.addWidget(self.textboxes["host"], 1, 0, 1, 2)
        server_section.grid.addWidget(self.buttons["scan_ports"], 1, 1)
        server_section.grid.addWidget(self.buttons["advanced_port"], 2, 0, 1, 2)
        server_section.grid.addWidget(self.buttons["connect"], 3, 0, 1, 2)

        control_section = CollapsibleSection("Scan controls")
        self.panel_sublayout.addWidget(control_section)
        self.num = 0
        control_section.grid.addWidget(self.mode, self.increment(), 0, 1, 2)
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
        self.settings_section.grid.addWidget(self.labels["start_range"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.labels["end_range"], self.num, 1)
        self.settings_section.grid.addWidget(self.textboxes["start_range"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["end_range"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["frequency"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["frequency"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["gain"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["gain"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["sweeps"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["sweeps"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["power_bins"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["power_bins"], self.num, 1)
        self.settings_section.grid.addWidget(self.labels["subsweeps"], self.increment(), 0)
        self.settings_section.grid.addWidget(self.textboxes["subsweeps"], self.num, 1)
        self.settings_section.grid.addWidget(self.profiles, self.increment(), 0, 1, 2)
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
        self.panel_scroll_area.setFrameShape(QFrame.StyledPanel)
        self.panel_scroll_area.setFixedWidth(375)
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
            mode = self.mode.currentText()
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
        conf = self.conf_defaults[self.mode.currentText()]
        self.textboxes["start_range"].setText("{:.2f}".format(conf["start_range"]))
        self.textboxes["end_range"].setText("{:.2f}".format(conf["end_range"]))
        self.textboxes["gain"].setText("{:.2f}".format(conf["gain"]))
        self.textboxes["frequency"].setText("{:d}".format(conf["frequency"]))
        self.sweep_count = -1
        self.textboxes["sweeps"].setText("-1")
        if self.profiles.isVisible():
            self.profiles.setCurrentIndex(0)

    def service_defaults_handler(self):
        mode = self.mode.currentText()
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
        mode = self.mode.currentText()
        if self.mode_to_param[mode] != self.mode_to_param[self.current_canvas]:
            self.data = None
            self.buttons["replay_buffered"].setEnabled(False)

        if force_update or self.current_canvas not in mode:
            self.main_layout.removeWidget(self.canvas)
            self.canvas.setParent(None)
            self.canvas.deleteLater()
            self.canvas = None
            refresh = False
            if self.current_canvas == mode:
                refresh = True
                self.update_service_params()
            self.canvas = self.init_graphs(mode, refresh=refresh)
            self.main_layout.addWidget(self.canvas, 0, 0)

        if "select service" not in mode.lower():
            self.update_sensor_config()

    def update_interface(self):
        if self.buttons["connect"].text() == "Disconnect":
            self.connect_to_server()

        if "serial" in self.interface.currentText().lower():
            self.ports.show()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].show()
            self.buttons["scan_ports"].show()
        elif "spi" in self.interface.currentText().lower():
            self.ports.hide()
            self.textboxes["host"].hide()
            self.buttons["advanced_port"].hide()
            self.buttons["scan_ports"].hide()
        else:  # socket
            self.ports.hide()
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
        if "Select" in self.mode.currentText():
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

        params = {
            "sensor_config": self.update_sensor_config(),
            "clutter_file": self.cl_file,
            "use_clutter": use_cl,
            "create_clutter": create_cl,
            "data_source": data_source,
            "data_type": self.mode_to_param[self.mode.currentText()],
            "service_type": self.mode.currentText(),
            "sweep_buffer": self.sweep_buffer,
            "service_params": self.update_service_params(),
        }

        self.threaded_scan = Threaded_Scan(params, parent=self)
        self.threaded_scan.sig_scan.connect(self.thread_receive)
        self.sig_scan.connect(self.threaded_scan.receive)

        self.buttons["start"].setEnabled(False)
        self.buttons["load_scan"].setEnabled(False)
        self.buttons["save_scan"].setEnabled(False)
        self.buttons["create_cl"].setEnabled(False)
        self.buttons["load_cl"].setEnabled(False)
        self.mode.setEnabled(False)
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
        self.mode.setEnabled(True)
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
            if "Select service" in self.current_canvas:
                self.mode.setCurrentIndex(2)

            if self.interface.currentText().lower() == "socket":
                host = self.textboxes["host"].text()
                self.client = JSONClient(host)
                statusbar_connection_info = "socket ({})".format(host)
            elif self.interface.currentText().lower() == "spi":
                self.client = RegSPIClient()
                statusbar_connection_info = "SPI"
            else:
                port = self.ports.currentText()
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
        conf, service = self.mode_to_config[self.mode.currentText()]
        mode = self.mode.currentText()

        if not conf:
            return None

        external = ("internal" not in service.lower())

        conf.sensor = int(self.textboxes["sensor"].text())
        if not refresh and external:
            self.textboxes["start_range"].setText("{:.2f}".format(conf.range_interval[0]))
            self.textboxes["end_range"].setText("{:.2f}".format(conf.range_interval[1]))
            self.textboxes["gain"].setText("{:.2f}".format(conf.gain))
            self.textboxes["frequency"].setText("{:d}".format(conf.sweep_rate))
            self.sweep_count = -1
        else:
            stitching = self.check_values(conf.mode)
            conf.experimental_stitching = stitching
            conf.range_interval = [
                    float(self.textboxes["start_range"].text()),
                    float(self.textboxes["end_range"].text()),
            ]
            conf.sweep_rate = int(self.textboxes["frequency"].text())
            conf.gain = float(self.textboxes["gain"].text())
            self.sweep_count = int(self.textboxes["sweeps"].text())
            if "power" in mode.lower():
                conf.bin_count = int(self.textboxes["power_bins"].text())
            if "sparse" in mode.lower():
                conf.number_of_subsweeps = int(self.textboxes["subsweeps"].text())
            if "envelope" in mode.lower():
                profile_text = self.profiles.currentText().lower()
                if "snr" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.MAX_SNR
                elif "depth" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.MAX_DEPTH_RESOLUTION
                elif "leakage" in profile_text:
                    conf.session_profile = configs.EnvelopeServiceConfig.DIRECT_LEAKAGE

        return conf

    def update_service_params(self):
        errors = []
        mode = self.mode.currentText()

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

    def check_values(self, mode):
        errors = []
        if not self.textboxes["frequency"].text().isdigit():
            errors.append("Frequency must be an integer and not less than 0!\n")
            self.textboxes["frequency"].setText("10")

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

        min_start_range = 0 if "leakage" in self.profiles.currentText().lower() else 0.06
        start = self.is_float(self.textboxes["start_range"].text(), is_positive=False)
        start, e = self.check_limit(start, self.textboxes["start_range"], min_start_range, 6.94)
        if e:
            errors.append("Start range must be between {}m and 6.94m!\n".format(min_start_range))

        end = self.is_float(self.textboxes["end_range"].text())
        end, e = self.check_limit(end, self.textboxes["end_range"], 0.12, 7)
        if e:
            errors.append("End range must be between 0.12m and 7.0m!\n")

        r = end - start

        env_max_range = 0.96
        iq_max_range = 0.72
        data_type = self.mode_to_param[self.mode.currentText()]
        if "iq" in data_type or "envelope" in data_type:
            if self.interface.currentText().lower() == "socket":
                env_max_range = 6.88
                iq_max_range = 6.88
            else:
                env_max_range = 5.0
                iq_max_range = 3.0

        stitching = False
        if r <= 0:
            errors.append("Range must not be less than 0!\n")
            self.textboxes["end_range"].setText(str(start + 0.06))
            end = start + 0.06
            r = end - start

        if "envelope" in data_type:
            if r > env_max_range:
                errors.append("Envelope range must be less than %.2fm!\n" % env_max_range)
                self.textboxes["end_range"].setText(str(start + env_max_range))
                end = start + env_max_range
                r = end - start
            elif r > 0.96:
                stitching = True

        if "iq" in data_type:
            if r > iq_max_range:
                errors.append("IQ range must be less than %.2fm!\n" % iq_max_range)
                self.textboxes["end_range"].setText(str(start + iq_max_range))
                end = start + iq_max_range
                r = end - start
            elif r > 0.72:
                stitching = True

        self.labels["stitching"].setVisible(stitching)
        self.textboxes["frequency"].setEnabled(not stitching)

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

                index = self.mode.findText(mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.mode.setCurrentIndex(index)

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
                    self.profiles.setCurrentIndex(f["profile"][()])
                    mode = self.mode.currentText()
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
                            float(self.textboxes["start_range"].text()),
                            float(self.textboxes["end_range"].text()),
                    ]
                    conf.sweep_rate = int(self.textboxes["frequency"].text())

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
                index = self.mode.findText(mode, QtCore.Qt.MatchFixedString)
                if index >= 0:
                    self.mode.setCurrentIndex(index)
                self.data = data

            self.textboxes["start_range"].setText(str(conf.range_interval[0]))
            self.textboxes["end_range"].setText(str(conf.range_interval[1]))
            self.textboxes["gain"].setText(str(conf.gain))
            self.textboxes["frequency"].setText(str(int(conf.sweep_rate)))
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
        mode = self.mode.currentText()
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
                    f.create_dataset("sweep_rate", data=int(self.textboxes["frequency"].text()),
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
                    f.create_dataset("profile", data=self.profiles.currentIndex(),
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
        elif "update_plots" in message_type:
            if data:
                self.update_plots(data)
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
        elif "process_data":
            self.advanced_process_data["process_data"] = data
        else:
            print("Thread data not implemented!")
            print(message_type, message, data)

    def update_plots(self, data):
        mode = self.mode.currentText()
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        xdim = data["hist_env"].shape[0]
        if not data["sweep"]:
            self.env_plot_max_y = 0
            self.envelope_plot_window.setXRange(xstart, xend)
            self.peak_text.setPos(xstart, 0)

            self.smooth_envelope = example_utils.SmoothMax(
                int(self.textboxes["frequency"].text()),
                tau_decay=1,
                tau_grow=0.2
                )

            if mode == "IQ":
                self.iq_plot_window.setXRange(xstart, xend)
                self.iq_plot_window.setYRange(-1.1, 1.1)

            yax = self.hist_plot_image.getAxis("left")
            y = np.round(np.arange(0, xdim+xdim/9, xdim/9))
            labels = np.round(np.arange(xstart, xend+(xend-xstart)/9,
                              (xend-xstart)/9))
            ticks = [list(zip(y, labels))]
            yax.setTicks(ticks)
            self.hist_plot_image.setYRange(0, xdim)

            s_buff = data["hist_env"].shape[1]
            t_buff = s_buff / data["sensor_config"].sweep_rate
            tax = self.hist_plot_image.getAxis("bottom")
            t = np.round(np.arange(0, s_buff + 1, s_buff/min(10, s_buff)))
            labels = np.round(t / s_buff * t_buff, decimals=3)
            ticks = [list(zip(t, labels))]
            tax.setTicks(ticks)

        peak = "Peak: N/A"
        if data["peaks"]["peak_mm"]:
            self.env_peak_vline.setValue(data["peaks"]["peak_mm"])
            peak = "Peak: %.1fmm" % data["peaks"]["peak_mm"]
            if data["snr"] and np.isfinite(data["snr"]):
                peak = "Peak: %.1fmm, SNR: %.1fdB" % (data["peaks"]["peak_mm"], data["snr"])

        self.peak_text.setText(peak, color=(1, 1, 1))

        max_val = max(np.max(data["env_clutter"]+data["env_ampl"]), np.max(data["env_clutter"]))
        peak_line = np.flip((data["hist_plot"]-xstart)/(xend - xstart)*xdim, axis=0)

        self.envelope_plot.setData(data["x_mm"], data["env_ampl"] + data["env_clutter"])
        self.clutter_plot.setData(data["x_mm"], data["env_clutter"])

        ymax_level = min(1.5*np.max(np.max(data["hist_env"])), self.env_plot_max_y)

        self.hist_plot.updateImage(data["hist_env"].T, levels=(0, ymax_level))
        self.hist_plot_peak.setData(peak_line)
        self.hist_plot_peak.setZValue(2)

        self.envelope_plot_window.setYRange(0, self.smooth_envelope.update(max_val))
        if mode == "IQ":
            self.iq_plot.setData(data["x_mm"], data["phase"])

        if max_val > self.env_plot_max_y:
            self.env_plot_max_y = 1.2 * max_val

    def update_power_plots(self, data):
        xstart = data["x_mm"][0]
        xend = data["x_mm"][-1]
        if not data["sweep"]:
            bin_num = int(self.textboxes["power_bins"].text())
            bin_width = (xend - xstart)/(bin_num + 1)
            self.env_plot_max_y = 0
            self.power_plot_window.setXRange(xstart, xend)
            self.power_plot.setOpts(x=data["x_mm"], width=bin_width)
            self.power_plot_window.setXRange(xstart - bin_width / 2,
                                             xend + bin_width / 2)
            self.smooth_power = example_utils.SmoothMax(
                int(self.textboxes["frequency"].text()),
                tau_decay=1,
                tau_grow=0.2
                )
        self.power_plot.setOpts(height=data["iq_data"])
        self.power_plot_window.setYRange(0, self.smooth_power.update(np.max(data["iq_data"])))

    def update_sparse_plots(self, data):
        if not data["sweep"]:
            self.smooth_sparse = example_utils.SmoothMax(
                int(self.textboxes["frequency"].text()),
                tau_decay=1,
                tau_grow=0.2
                )

            axs = {}

            xstart = data["x_mm"][0]
            xend = data["x_mm"][-1]
            xdim = data["hist_env"].shape[1]
            data_points = min(xdim, 10)
            x = np.round(np.arange(0, xdim+xdim/data_points, xdim/data_points))
            labels = np.round(np.arange(xstart, xend+(xend-xstart)/data_points,
                              (xend-xstart)/data_points))
            axs["left"] = [list(zip(x, labels))]

            s_buff = data["hist_env"].shape[0]
            t_buff = s_buff / data["sensor_config"].sweep_rate

            t = np.round(np.arange(0, s_buff + 1, s_buff/min(10, s_buff)))
            labels = np.round(t / s_buff * t_buff, decimals=3)
            axs["bottom"] = [list(zip(t, labels))]

            for ax in axs:
                xax = self.hist_plot_image.getAxis(ax)
                xax.setTicks(axs[ax])
                xax = self.hist_move_image.getAxis(ax)
                xax.setTicks(axs[ax])

        self.sparse_plot.setData(data["x_mm"], data["iq_data"])
        m = self.smooth_sparse.update(max(2500, np.amax(np.abs(data["iq_data"]))))
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
        old_start = float(self.textboxes["start_range"].text())
        old_end = float(self.textboxes["end_range"].text())
        start = data["actual_range_start"]
        self.textboxes["start_range"].setText("{:.2f}".format(start))
        end = start + data["actual_range_length"]
        self.textboxes["end_range"].setText("{:.2f}".format(end))
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
                self.profiles.setCurrentIndex(last_config["profile"])
                self.textboxes["sweep_buffer"].setText(last_config["sweep_buffer"])
                self.textboxes["sensor"].setText("{:d}".format(sensor_config.sensor[0]))
                self.interface.setCurrentIndex(last_config["interface"])
                self.ports.setCurrentIndex(last_config["port"])
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
            self.textboxes["frequency"].setText(str(int(sensor_config.sweep_rate)))
            self.textboxes["start_range"].setText("{:.2f}".format(sensor_config.range_interval[0]))
            self.textboxes["end_range"].setText("{:.2f}".format(sensor_config.range_interval[1]))
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
        if "select" not in str(self.mode.currentText()).lower():
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
                "interface": self.interface.currentIndex(),
                "port": self.ports.currentIndex(),
                "profile": self.profiles.currentIndex(),
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
                self.emit("client_error", "Failed to communicate with server!\n"
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
