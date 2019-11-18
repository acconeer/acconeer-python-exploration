from argparse import ArgumentParser
import signal
import numpy as np
from datetime import datetime
import logging
import sys
import time
import serial.tools.list_ports
import pyqtgraph as pg
from PyQt5 import QtCore


class ExampleArgumentParser(ArgumentParser):
    def __init__(self, num_sens="+"):
        super().__init__()

        server_group = self.add_mutually_exclusive_group(required=True)
        server_group.add_argument(
            "-u",
            "--uart",
            metavar="port",
            dest="serial_port",
            help="connect via uart (using register-based protocol)",
            nargs="?",
            const="",  # as argparse does not support setting const to None
            )
        server_group.add_argument(
            "-s",
            "--socket",
            metavar="address",
            dest="socket_addr",
            help="connect via socket on given address (using json-based protocol)",
            )
        server_group.add_argument(
            "-spi",
            "--spi",
            dest="spi",
            help="connect via spi (using register-based protocol)",
            action="store_true",
            )

        self.add_argument(
            "--sensor",
            metavar="id",
            dest="sensors",
            type=int,
            default=[1],
            nargs=num_sens,
            help="the sensor(s) to use (default: 1)",
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
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def config_logging(args=None, level=logging.WARN):
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


def autodetect_serial_port():
    port_infos = serial.tools.list_ports.comports()

    for port_info in port_infos:
        port, desc, _ = port_info
        if desc.strip().lower() in ["xb112", "xb122"]:
            print("Autodetected {} on {}\n".format(desc.strip(), port))
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


def color_cycler(i=0):
    category10 = [
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
    ]

    return category10[i % len(category10)]


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
        self.tau_decay = tau_decay
        self.tau_grow = tau_grow

        self.last_t = 0
        self.x = -1
        self.y = -1

    def update(self, m):
        m = max(m, 1e-12)

        if self.fixed_dt is None:
            now = time.time()
            dt = now - self.last_t
            self.last_t = now
        else:
            dt = self.fixed_dt

        ax = np.exp(-dt / self.tau_decay) if self.tau_decay > 1e-3 else 0
        ay = np.exp(-dt / self.tau_grow) if self.tau_grow > 1e-3 else 0

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
    plot.setXRange(-s*max_r, s*max_r)
    plot.setYRange(-s*max_r, s*max_r)

    for i, r in enumerate(np.linspace(0, max_r, 5)[1:]):
        circle = pg.QtGui.QGraphicsEllipseItem(-r, -r, r*2, r*2)
        circle.setPen(pg.mkPen("k" if i == 3 else 0.5))
        plot.addItem(circle)

        if i == 3:
            text_item = pg.TextItem(text=str(r), color="k", anchor=(0, 1))
            text_item.setPos(np.cos(np.pi/8)*r, np.sin(np.pi/8)*r)
            plot.addItem(text_item)

    for i in range(8):
        deg = (360 / 8) * i
        rad = np.radians(deg)
        x = np.cos(rad)
        y = np.sin(rad)
        text = str(int(deg)) + '\u00b0'
        ax = (-x + 1) / 2
        ay = (y + 1) / 2
        text_item = pg.TextItem(text, color="k", anchor=(ax, ay))
        text_item.setPos(max_r*x*1.02, max_r*y*1.02)
        plot.addItem(text_item)
        plot.plot([0, max_r*x], [0, max_r*y], pen=pg.mkPen(0.5))


def pg_mpl_cmap(name):
    import matplotlib.pyplot as plt
    cmap = plt.get_cmap(name)
    cmap._init()
    return np.array(cmap._lut) * 255


class FreqCounter:
    def __init__(self, a=0.95, num_bits=None):
        self.a = a
        self.num_bits = num_bits
        self.last_t = None
        self.lp_dt = None

    def tick(self):
        now = time.time()

        if self.last_t:
            dt = now - self.last_t
            if self.lp_dt:
                self.lp_dt = self.a * self.lp_dt + (1-self.a) * dt
                f = 1/self.lp_dt
                dt_ms = self.lp_dt * 1e3
                if self.num_bits:
                    data_rate = self.num_bits * f * 1e-6
                    s = " {:5.1f} ms, {:5.1f} Hz, {:5.2f} Mbit/s".format(dt_ms, f, data_rate)
                    print(s, end="\r")
                else:
                    print(" {:5.1f} ms, {:5.1f} Hz".format(dt_ms, f), end="\r")
            else:
                self.lp_dt = dt

        self.last_t = now
