# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import copy
import logging
import math
import operator
import signal
import struct
import sys
import time
from datetime import datetime
from types import ModuleType
from typing import Any, Generic, TypeVar, overload

import numpy as np
import numpy.typing as npt
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
    PROMPT = "Press Ctrl-C to end session"

    def __init__(self, prompt: str | None = PROMPT) -> None:
        self._signal_count = 0
        signal.signal(signal.SIGINT, self.interrupt_handler)
        if prompt is not None:
            print(prompt, flush=True)

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
        m = max(np.nan_to_num(np.nanmax(data)), 1e-12)

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


@overload
def polar_to_cartesian(length: float, angle: float) -> tuple[float, float]: ...


@overload
def polar_to_cartesian(
    length: npt.NDArray[np.float64], angle: npt.NDArray[np.float64]
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]: ...


def polar_to_cartesian(length: Any, angle: Any) -> tuple[Any, Any]:
    """Transforms a polar coordinate (length, angle in radians) to (x, y).

    ``angle`` is measured from +x toward +y. Inputs may be scalars or numpy
    arrays of broadcast-compatible shape; the return tuple matches the input
    kind.
    """
    return length * np.cos(angle), length * np.sin(angle)


@overload
def spherical_to_cartesian(length: float, az: float, el: float) -> tuple[float, float, float]: ...


@overload
def spherical_to_cartesian(
    length: npt.NDArray[np.float64],
    az: npt.NDArray[np.float64],
    el: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]: ...


def spherical_to_cartesian(length: Any, az: Any, el: Any) -> tuple[Any, Any, Any]:
    """
    Transforms a spherical coordinate (length, az, el) (angles in radians) to (x, y, z).

    - boresight (az=0, el=0) lies on +y
    - +az rotates toward +x (``x = length·sin(az)``), independent of elevation;
      clockwise seen from above, i.e. left-handed about +z
    - +el rotates toward +z

    Inputs may be scalars or numpy arrays of broadcast-compatible shape; the
    return tuple matches the input kind.
    """
    cos_az = np.cos(az)
    return (
        length * np.sin(az),
        length * cos_az * np.cos(el),
        length * cos_az * np.sin(el),
    )


@overload
def cartesian_to_spherical(x: float, y: float, z: float) -> tuple[float, float, float]: ...


@overload
def cartesian_to_spherical(
    x: npt.NDArray[np.float64],
    y: npt.NDArray[np.float64],
    z: npt.NDArray[np.float64],
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], npt.NDArray[np.float64]]: ...


def cartesian_to_spherical(x: Any, y: Any, z: Any) -> tuple[Any, Any, Any]:
    """
    Transforms a Cartesian coordinate (x, y, z) to (length, az, el) (angles in radians).

    Inverse of :func:`spherical_to_cartesian`, with the same convention:

    - boresight (az=0, el=0) lies on +y
    - az is the angle off the yz-plane toward +x (``az = atan2(x, sqrt(y² + z²))``)
    - el is the angle in the yz-plane off +y toward +z (``el = atan2(z, y)``)

    The inverse is single-valued for ``y > 0``, i.e. in front of the sensor.
    Inputs may be scalars or numpy arrays of broadcast-compatible shape; the
    return tuple matches the input kind.
    """
    return (
        np.sqrt(x**2 + y**2 + z**2),
        np.arctan2(x, np.sqrt(y**2 + z**2)),
        np.arctan2(z, y),
    )


def spherical_to_cartesian_jacobian(x: float, y: float, z: float) -> npt.NDArray[np.float64]:
    """Jacobian of :func:`spherical_to_cartesian` at the Cartesian point (x, y, z).

    Returns the 3x3 matrix with columns ``d/d(length)``, ``d/d(az)`` and
    ``d/d(el)`` of ``(x, y, z)``. It is built from ``(x, y, z)`` directly,
    using ``sin(az) = x / length``, ``cos(az) = rho / length``,
    ``sin(el) = z / rho`` and ``cos(el) = y / rho`` with ``rho = hypot(y, z)``.

    :raises ValueError: If ``rho`` is zero, as elevation is undefined on the
        x-axis.
    """
    rho = math.hypot(y, z)
    if rho == 0.0:
        msg = "spherical_to_cartesian_jacobian is undefined on the x-axis"
        raise ValueError(msg)
    length = math.hypot(x, rho)
    return np.array(
        [
            [x / length, rho, 0.0],
            [y / length, -x * y / rho, -z],
            [z / length, -x * z / rho, y],
        ]
    )


def _draw_outgoing_polar_line(plot, deg, length):
    """Plots a line in the 'polar grid'

    The line is the line going from the center with the angle ``deg`` (in degrees)
    and length ``length``
    A text with the angle in degrees is also added at the line's tip.
    """
    DEGREE_SYMBOL = "\u00b0"

    x, y = polar_to_cartesian(length, np.radians(deg))
    unit_x, unit_y = polar_to_cartesian(1, np.radians(deg))
    anchor = ((-unit_x + 1) / 2, (unit_y + 1) / 2)

    text_item = pg.TextItem(f"{deg:.0f}{DEGREE_SYMBOL}", color="k", anchor=anchor)
    text_item.setPos(x * 1.02, y * 1.02)

    plot.addItem(text_item)
    plot.plot([0, x], [0, y], pen=pg.mkPen(0.5))


def pg_setup_polar_plot(plot, max_r=1, degree_start=0, degree_span=360, range_suffix=""):
    plot.showAxis("left", False)
    plot.showAxis("bottom", False)
    plot.setAspectLocked()
    plot.disableAutoRange()

    radians = [math.radians(deg) for deg in range(degree_start, degree_start + degree_span)]
    xs = [math.cos(r) for r in radians]
    ys = [math.sin(r) for r in radians]
    s = 1.15
    plot.setXRange(s * min(xs + [0]) * max_r, s * max(xs + [0]) * max_r)
    plot.setYRange(s * min(ys + [0]) * max_r, s * max(ys + [0]) * max_r)

    for i, r in enumerate(np.linspace(0, max_r, 5)[1:]):
        circle = pg.QtWidgets.QGraphicsEllipseItem(-r, -r, r * 2, r * 2)

        # The unit of these are degrees * 16.
        # (See https://doc.qt.io/qt-6/qgraphicsellipseitem.html#setStartAngle)
        #   The span goes clock-wise while we want to express it
        # counter clock-wise (hence the negation).
        circle.setStartAngle(-degree_start * 16)

        circle.setSpanAngle(-degree_span * 16)

        circle.setPen(pg.mkPen("k" if i == 3 else 0.5))
        plot.addItem(circle)

        if i == 3:
            text_item = pg.TextItem(text=f"{r:.2f} {range_suffix}", color="k", anchor=(0, 1))
            text_item.setPos(np.cos(np.pi / 8) * r, np.sin(np.pi / 8) * r)
            plot.addItem(text_item)

    # plot lines that are mutliple of 45 deg if they are in the specified span
    for i in range(8):
        start_offset = (degree_start // 45) * 45
        deg = start_offset + (360 / 8) * i

        if not (degree_start <= deg <= degree_start + degree_span):
            continue

        _draw_outgoing_polar_line(plot, deg, max_r)

    # plot extremes if they're not already plotted.
    if degree_start % 45 != 0:
        _draw_outgoing_polar_line(plot, degree_start, max_r)

    if degree_span % 45 != 0:
        _draw_outgoing_polar_line(plot, degree_start + degree_span, max_r)


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
