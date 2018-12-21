from argparse import ArgumentParser
import signal
import numpy as np
from datetime import datetime
import logging
import sys
import serial.tools.list_ports


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


def config_logging(args):
    fmt = "[%(asctime)s] %(levelname)s - %(name)s - %(message)s"
    datefmt = "%H:%M:%S"

    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    elif args.quiet:
        level = logging.ERROR
    else:
        level = logging.WARN

    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter(fmt, datefmt=datefmt)
    stream_handler.setFormatter(formatter)
    log = logging.getLogger(__name__.split(".")[0])
    log.setLevel(level)
    log.addHandler(stream_handler)

    logging.getLogger(__name__).debug("logging configured")


def autodetect_serial_port():
    port_infos = serial.tools.list_ports.comports()

    for port_info in port_infos:
        port, desc, _ = port_info
        if desc.startswith("XB112"):
            print("Autodetected XB112 on {}\n".format(port))
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
