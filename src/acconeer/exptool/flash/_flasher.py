import argparse

import serial

import acconeer.exptool as et
from acconeer.exptool.flash._products import PRODUCT_FLASH_MAP


def flash_image(image_path, flash_port):
    if flash_port:
        if flash_port.pid in PRODUCT_FLASH_MAP.keys():
            PRODUCT_FLASH_MAP[flash_port.pid].flash(flash_port.device, image_path)
        else:
            print(f"No flash support for Acconeer device {flash_port.product}")


def find_flash_port(port=None):
    flash_port = None
    detected_ports = [
        pinfo
        for pinfo in et.utils.tag_serial_ports_objects(serial.tools.list_ports.comports())
        if pinfo[1]
    ]

    if len(detected_ports) == 0:
        print("No devices connected")
    elif port:
        for pinfo in detected_ports:
            if port == pinfo[0].device:
                flash_port = pinfo[0]
        if not flash_port:
            print(f"No device connected to port {port}")
    elif len(detected_ports) == 1:
        flash_port = detected_ports[0][0]
    elif len(detected_ports) > 1:
        print("Found multiple Acconeer products:", end="\n\n")
        detected_ports = [(p.device, t) for (p, t) in detected_ports]
        for port, tag in [("Serial port:", "Model:")] + detected_ports:
            print(f"\t{port:<15} {tag:}")
        print('\nRun the script again and specify port using the "--serial-port" flag.')

    return flash_port


def main():
    parser = argparse.ArgumentParser(description="Image Flasher")
    parser.add_argument(
        "--serial-port",
        dest="serial_port",
        metavar="port",
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

    flash_port = find_flash_port(args.serial_port)

    flash_image(args.image, flash_port)
