# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import copy
import logging
import operator
import signal
import struct
import sys
import time
from datetime import datetime
from types import ModuleType
from typing import Generic, TypeVar

import numpy as np
import serial.tools.list_ports

from acconeer.exptool._core.communication.comm_devices import (
    get_serial_devices,
    tag_serial_ports_objects,
)


try:
    from PySide6 import QtCore
except ImportError:
    QtCore = None

try:
    import pyqtgraph as pg
except ImportError:
    pg = None

S = TypeVar("S")
T = TypeVar("T")
DTypeT = TypeVar("DTypeT")


class ExampleInterruptHandler:
    def __init__(self):
        self._signal_count = 0
        signal.signal(signal.SIGINT, self.interrupt_handler)

    @property
    def got_signal(self):
        return self._signal_count > 0

    def force_signal_interrupt(self):
        self.interrupt_handler(signal.SIGINT, None)

    def interrupt_handler(self, signum, frame):
        self._signal_count += 1
        if self._signal_count >= 3:
            raise KeyboardInterrupt


def mpl_setup_yaxis_for_phase(ax):
    ax.set_ylim(-np.pi, np.pi)
    ax.set_yticks(np.linspace(-np.pi, np.pi, 5))
    ax.set_yticklabels([r"$-\pi$", r"$-\pi/2$", r"0", r"$\pi/2$", r"$\pi$"])


def timestamp():
    """Get the current date and time formatted as 1999-12-31_23-59-59"""

    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def config_logging(args=None, level=logging.WARNING):
    fmt = "{asctime}.{msecs:03.0f} | {levelname:<7} | {processName:<16} | {name:<36} | {message}"
    datefmt = "%H:%M:%S"

    if args is not None:
        if args.debug:
            level = logging.DEBUG
        elif args.verbose:
            level = logging.INFO
        elif args.quiet:
            level = logging.ERROR

    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt, datefmt=datefmt, style="{")
    stream_handler.setFormatter(formatter)
    log = logging.getLogger(__name__.split(".")[0])
    log.setLevel(level)
    log.addHandler(stream_handler)

    logging.getLogger(__name__).debug("logging configured")


def set_loglevel(level):
    log = logging.getLogger(__name__.split(".")[0])
    log.setLevel(level)


def tag_serial_ports(port_infos):
    """
    Returns every port and Acconeer model number in a tuple if it's an
    Acconeer product.

    E.g:
    [ ("/dev/ttyUSB0", None),   <- Not an Acconeer product
      ("/dev/ttyUSB1", "XB112") <- An Acconeer product
    ]

    :param port_infos: Information about ports as given by
        `serial.tools.list_ports.comports()`
    :returns: List of tuples [(<port>, <model number> or None), ...]
    """
    port_tag_tuples = tag_serial_ports_objects(port_infos)
    port_tag_tuples = [(port.device, tag) for (port, tag) in port_tag_tuples]
    return port_tag_tuples


def get_tagged_serial_ports():
    tagged_serial_ports = []
    serial_devices = get_serial_devices()
    for serial_device in serial_devices:
        tagged_serial_ports.append((serial_device.port, serial_device.name))
    return tagged_serial_ports


def autodetect_serial_port():
    port_infos = serial.tools.list_ports.comports()

    tagged_serial_ports = tag_serial_ports(port_infos)
    acconeer_port_infos = [pinfo for pinfo in tagged_serial_ports if pinfo[1]]

    # Check for mutliple Acconeer devices;
    if len(acconeer_port_infos) > 1:
        print("Found multiple Acconeer products:", end="\n\n")
        for port, tag in [("Serial port:", "Model:")] + acconeer_port_infos:
            print(f"\t{port:<15} {tag:}")
        print('\nRun the script again and specify port using the "-u"/"--uart" flag.')
        sys.exit()

    if len(acconeer_port_infos) == 1:
        port, tag = acconeer_port_infos[0]
        print("Autodetected {} on {}\n".format(tag, port))
        return port

    for port_info in port_infos:
        port, desc, _ = port_info
        if desc == "FT230X Basic UART":
            print("Autodetected FT230X Basic UART on {}\n".format(port))
            return port

    if len(port_infos) == 0:
        print("Could not autodetect serial port, no ports available")
        sys.exit()
    elif len(port_infos) == 1:
        print("Autodetected single available serial port on {}\n".format(port))
        return port_infos[0][0]
    else:
        print("Multiple serial ports are available:")
        for port_info in port_infos:
            port, desc, _ = port_info
            print("  {:<13}  ({})".format(port, desc))
        print("\nRe-run the script with a given port")
        sys.exit()

    print("Could not autodetect serial port")
    sys.exit()


def get_module_version(module: ModuleType) -> str:
    if hasattr(module, "__version__"):
        return str(module.__version__)
    else:
        msg = f"Unknown module version for {module.__name__}"
        raise AttributeError(msg)


def color_cycler(i=0):
    category12 = [
        "#1f77b4",
        "#ff7f0e",
        "#2ca02c",
        "#d62728",
        "#9467bd",
        "#8c564b",
        "#e377c2",
        "#7f7f7f",
        "#bcbd22",
        "#17becf",
        "#e6ab02",
        "#f516bd",
    ]

    return category12[i % len(category12)]


def pg_pen_cycler(i=0, style=None, width=2):
    pen = pg.mkPen(color_cycler(i), width=width)
    if style == "--":
        pen.setStyle(QtCore.Qt.DashLine)
    elif style is not None:
        pen.setStyle(style)
    return pen


def pg_brush_cycler(i=0):
    return pg.mkBrush(color_cycler(i))


class SmoothMax:
    def __init__(self, f=None, hysteresis=0.5, tau_decay=2.0, tau_grow=0.5):
        self.fixed_dt = 1 / f if (f is not None and f > 0) else None
        self.hyst = hysteresis
        self.tc_decay = tau_decay
        self.tc_grow = tau_grow

        self.last_t = 0
        self.x = self.y = -1

    def update(self, data):
        m = max(np.nanmax(data), 1e-12)

        if self.fixed_dt is None:
            now = time.perf_counter()
            dt = now - self.last_t
            self.last_t = now
        else:
            dt = self.fixed_dt

        ax = np.exp(-dt / self.tc_decay) if self.tc_decay > 1e-3 else 0
        ay = np.exp(-dt / self.tc_grow) if self.tc_grow > 1e-3 else 0

        if m > self.x:
            self.x = m
        else:
            self.x = (1 - ax) * m + ax * self.x

        if self.y < 0:
            self.y = self.x
        elif self.x > self.y:
            self.y = (1 - ay) * self.x * (1 + self.hyst) + ay * self.y
        elif self.x < (1 - self.hyst) * self.y:
            self.y = self.x / (1 - self.hyst)

        return self.y


class SmoothLimits:
    def __init__(self, f=None, hysteresis=0.3, tau_decay=1.5, tau_grow=0.3):
        self.fixed_dt = 1 / f if (f is not None and f > 0) else None
        self.hyst = hysteresis
        self.tc_decay = tau_decay
        self.tc_grow = tau_grow

        self.last_t = 0
        self.x = self.y = self.z = None

    def update(self, data):
        data_lims = (np.nanmin(data), np.nanmax(data))

        if self.fixed_dt is None:
            now = time.perf_counter()
            dt = now - self.last_t
            self.last_t = now
        else:
            dt = self.fixed_dt

        if self.x is None:  # First call
            self.x = list(data_lims)
            self.y = list(data_lims)
            self.z = list(data_lims)
            return list(data_lims)

        ad = np.exp(-dt / self.tc_decay) if self.tc_decay > 1e-3 else 0
        ag = np.exp(-dt / self.tc_grow) if self.tc_grow > 1e-3 else 0

        ops = (operator.lt, operator.gt)
        idxs = (0, 1)

        for op, i in zip(ops, idxs):
            if op(data_lims[i], self.x[i]):
                self.x[i] = data_lims[i]
            else:
                self.x[i] = (1 - ad) * data_lims[i] + ad * self.x[i]

        for op, i in zip(ops, idxs):
            if op(self.x[i], self.y[i]):
                self.y[i] = (1 - ag) * self.x[i] + ag * self.y[i]
            else:
                self.y[i] = self.x[i]

        for op, i, j in zip(ops, idxs, reversed(idxs)):
            y_hyst = self.y[i] + (self.y[i] - self.y[j]) * (1 / (1 - self.hyst) - 1)

            if op(self.y[i], self.z[i]):
                self.z[i] = self.y[i]
            elif op(self.z[i], y_hyst):
                self.z[i] = y_hyst

        return self.z


pg_phase_ticks = [
    list(zip(np.linspace(-np.pi, np.pi, 5), ["-π", "-π/2", "0", "π/2", "π"])),
    [(x, "") for x in np.linspace(-np.pi, np.pi, 9)],
]


def pg_setup_polar_plot(plot, max_r=1):
    plot.showAxis("left", False)
    plot.showAxis("bottom", False)
    plot.setAspectLocked()
    plot.disableAutoRange()
    s = 1.15
    plot.setXRange(-s * max_r, s * max_r)
    plot.setYRange(-s * max_r, s * max_r)

    for i, r in enumerate(np.linspace(0, max_r, 5)[1:]):
        circle = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
        circle.setPen(pg.mkPen("k" if i == 3 else 0.5))
        plot.addItem(circle)

        if i == 3:
            text_item = pg.TextItem(text=str(r), color="k", anchor=(0, 1))
            text_item.setPos(np.cos(np.pi / 8) * r, np.sin(np.pi / 8) * r)
            plot.addItem(text_item)

    for i in range(8):
        deg = (360 / 8) * i
        rad = np.radians(deg)
        x = np.cos(rad)
        y = np.sin(rad)
        text = str(int(deg)) + "\u00b0"
        ax = (-x + 1) / 2
        ay = (y + 1) / 2
        text_item = pg.TextItem(text, color="k", anchor=(ax, ay))
        text_item.setPos(max_r * x * 1.02, max_r * y * 1.02)
        plot.addItem(text_item)
        plot.plot([0, max_r * x], [0, max_r * y], pen=pg.mkPen(0.5))


def pg_mpl_cmap(name):
    import matplotlib.pyplot as plt

    cmap = plt.get_cmap(name)
    cmap._init()
    return (np.array(cmap._lut) * 255).astype(np.uint8)


class FreqCounter:
    """
    Helper class for measuring & calculating temporal information:
        * time between ticks (lp-filtered), `FreqCounter.lp_dt`
        * frequency
        * data throughput (if num_bits is not None)
    """

    def __init__(self, a=None, tc=None, num_bits=None):
        assert (a is None) or (tc is None)

        if (a is None) and (tc is None):
            tc = 1.0

        self.a = a
        self.tc = tc
        self.num_bits = num_bits
        self.avg_dt_buf_len = 150  # Chosen after empirical testing
        self.reset()

    def reset(self):
        self.last_t = None
        self.lp_avg_dt = None
        self.num_ticks = 0
        self.avg_dt_buf = np.full(self.avg_dt_buf_len, np.nan)

    def tick_values(self):
        """
        Ticks the FreqCounter by taking the time delta from last time this was called.
        The update is done by a running average over the last 5 sweeps.
        The averaged value is passed through a lp_filter to avoid displaying blinking numbers.

        OBS! The first call to this method will return None.

        :returns:
            3-tuple of (delta time (averaged and lp-filtered), frequency, [throughput])
            -- OR --
            None
        """

        now = time.perf_counter()

        if self.last_t is None:
            self.last_t = now
            return None

        dt = now - self.last_t

        self.avg_dt_buf = np.roll(self.avg_dt_buf, -1)
        self.avg_dt_buf[-1] = dt

        avg_dt = np.nanmean(self.avg_dt_buf)

        if self.a is not None:
            a = self.a
        else:
            a = np.exp(-avg_dt / self.tc)

        a = min(a, 1.0 - 1.0 / (1.0 + self.num_ticks))

        if self.lp_avg_dt is None:
            self.lp_avg_dt = avg_dt
        else:
            self.lp_avg_dt = a * self.lp_avg_dt + (1 - a) * avg_dt

        self.last_t = now
        self.num_ticks += 1

        f = 1 / self.lp_avg_dt

        if self.num_bits is None:
            data_rate = None
        else:
            data_rate = self.num_bits * f

        return self.lp_avg_dt, f, data_rate

    def tick(self):
        """
        Prints the values returned by `tick_values()`.
        """
        tick_info = self.tick_values()
        if tick_info is None:
            return

        dt, f, data_rate = tick_info
        dt_ms = dt * 1e3
        data_rate_mbps = data_rate * 1e-6

        if data_rate is None:
            print(" {:5.1f} ms, {:5.1f} Hz".format(dt_ms, f), end="\r")
        else:
            s = " {:5.1f} ms, {:5.1f} Hz, {:5.2f} Mbit/s".format(dt_ms, f, data_rate_mbps)
            print(s, end="\r")


def hex_to_rgb_tuple(hex_color):
    return struct.unpack("BBB", bytes.fromhex(hex_color.lstrip("#")))


def is_power_of_2(n):
    return (n & (n - 1) == 0) and n != 0


def optional_or_else(value, default):
    return default if value is None else value


class PhonySeries(Generic[T]):
    def __init__(self, prototype: T, is_prototype_singleton: bool = True) -> None:
        self._prototype = prototype
        self._is_prototype_singleton = is_prototype_singleton

    def __next__(self) -> T:
        if self._is_prototype_singleton:
            return self._prototype
        else:
            return copy.copy(self._prototype)

    def __iter__(self) -> PhonySeries:
        return self
