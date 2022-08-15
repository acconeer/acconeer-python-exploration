# Copyright (c) Acconeer AB, 2022
# All rights reserved

import argparse
import platform

import serial

import acconeer.exptool as et
from acconeer.exptool.flash._products import PRODUCT_FLASH_MAP


def flash_image(image_path, flash_port):
    if flash_port:
        if isinstance(flash_port, et.utils.USBDevice):
            flash_pid = flash_port.pid
            flash_device = flash_port
            flash_product = flash_port.name
        else:
            flash_pid = flash_port.pid
            flash_device = flash_port.device
            flash_product = flash_port.product

        if flash_pid in PRODUCT_FLASH_MAP.keys():
            PRODUCT_FLASH_MAP[flash_pid].flash(flash_device, image_path)
        else:
            raise NotImplementedError(f"No flash support for Acconeer device {flash_product}")
    else:
        raise ValueError("Flash port is None")


def find_flash_port(port=None):
    flash_port = None
    detected_ports = [
        pinfo
        for pinfo in et.utils.tag_serial_ports_objects(serial.tools.list_ports.comports())
        if pinfo[1]
    ]

    if len(detected_ports) == 0 and platform.system().lower() == "windows":
        detected_ports = et.utils.get_usb_devices()

    if len(detected_ports) == 0:
        print("No devices connected")
    elif port:
        for pinfo in detected_ports:
            if isinstance(pinfo, et.utils.USBDevice):
                if port == pinfo:
                    flash_port = pinfo
            elif port == pinfo[0].device:
                flash_port = pinfo[0]
        if not flash_port:
            print(f"{port} in not connected")
    elif len(detected_ports) == 1:
        if isinstance(detected_ports[0], et.utils.USBDevice):
            flash_port = detected_ports[0]
        else:
            flash_port = detected_ports[0][0]
    elif len(detected_ports) > 1:
        print("Found multiple Acconeer products:", end="\n\n")
        if isinstance(detected_ports[0], et.utils.USBDevice):
            for port in detected_ports:
                print(f"\t{port.name}")
        else:
            detected_ports = [(p.device, t) for (p, t) in detected_ports]
            for port, tag in [("Serial port:", "Model:")] + detected_ports:
                print(f"\t{port:<15} {tag:}")
        print('\nRun the script again and specify port using the "--port" flag.')

    return flash_port


def main():
    parser = argparse.ArgumentParser(description="Image Flasher")
    parser.add_argument(
        "--port", dest="port", metavar="port", help="Serial port or USB device name"
    )
    parser.add_argument("--image", "-i", required=True, help="Image file to flash")

    verbosity_group = parser.add_mutually_exclusive_group(required=False)
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

    args = parser.parse_args()

    et.utils.config_logging(args)

    flash_port = find_flash_port(args.port)

    flash_image(args.image, flash_port)
