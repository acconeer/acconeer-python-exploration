# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import argparse
import getpass
import logging
import tempfile
import time
from typing import Optional

import serial

import acconeer.exptool as et
from acconeer.exptool.flash._bin_fetcher import (
    BIN_FETCH_PROMPT,
    clear_cookies,
    download,
    get_content,
    get_cookies,
    is_redirected_to_login_page,
    login,
    save_cookies,
)
from acconeer.exptool.flash._products import PRODUCT_FLASH_MAP

from ._dev_license import DevLicense
from ._dev_license_tui import DevLicenseTuiDialog


log = logging.getLogger(__name__)


def _query_yes_no(question: str, default: str = "yes") -> bool:
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
            It must be "yes" (the default), "no" or None (meaning
            an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        print(question + prompt, end="", flush=True)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' " "(or 'y' or 'n').\n")


def flash(bin_path: str, port: Optional[str] = None) -> None:

    log.debug("Flashing image..")

    flash_port = find_flash_port(port=port)
    try:
        flash_image(image_path=bin_path, flash_port=flash_port)
    except Exception as e:
        log.error(str(e))


def _failed_autodetect():
    raise Exception(
        "Device type couldn't be autodetected. Specify device type by using the --device flag."
    )


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


def find_flash_port(port=None, do_log=True):
    flash_port = None
    detected_ports = [
        pinfo
        for pinfo in et.utils.tag_serial_ports_objects(serial.tools.list_ports.comports())
        if pinfo[1]
    ]

    if len(detected_ports) == 0:
        detected_ports = et.utils.get_usb_devices()

    if len(detected_ports) == 0:
        if do_log:
            log.debug("No devices connected")
    elif port:
        for pinfo in detected_ports:
            if isinstance(pinfo, et.utils.USBDevice):
                if port == pinfo:
                    flash_port = pinfo
            elif port == pinfo[0].device:
                flash_port = pinfo[0]
        if not flash_port:
            raise Exception(f"Port {port} is not connected")
    elif len(detected_ports) == 1:
        if isinstance(detected_ports[0], et.utils.USBDevice):
            flash_port = detected_ports[0]
        else:
            flash_port = detected_ports[0][0]
    elif len(detected_ports) > 1:
        if do_log:
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
        "--port", dest="port", metavar="port", help="Serial port or USB device name."
    )
    parser.add_argument(
        "--device",
        "-d",
        dest="device",
        help="Device type. Only used if device type can't be autodetected.",
        choices=["XC120"],
    )
    parser.add_argument(
        "--clear-login", dest="clear", action="store_true", help="Clears saved login session."
    )

    image_group = parser.add_mutually_exclusive_group(required=False)
    image_group.add_argument("--image", "-i", dest="image", help="Image file to flash")
    image_group.add_argument(
        "--fetch",
        "-f",
        dest="fetch",
        action="store_true",
        help=(
            "Fetch latest image file from the web and flash it. "
            "Requires an Acconeer Developer Account."
        ),
    )
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

    if args.clear:
        clear_cookies()
        print("Saved login session cookie deleted!\n")

    if args.fetch:
        try:
            flash_port = find_flash_port(port=args.port)
            if args.device is None:
                if flash_port is not None:
                    if isinstance(flash_port, et.utils.USBDevice):
                        flash_product = flash_port.name
                    else:
                        flash_product = flash_port.product
                    if flash_product is None:
                        _failed_autodetect()
                    device = flash_product
                else:
                    _failed_autodetect()
            else:
                device = args.device

            cookies = get_cookies()
            new_login = False
            login_succeed = False
            while login_succeed is False:
                if cookies is None:
                    print("\n" + BIN_FETCH_PROMPT)
                    email = input("\nEmail: ")
                    password = getpass.getpass("Password: ")
                    new_login = True
                    cookies = login(email, password)

                print("\nLogging in... ", end="", flush=True)
                login_succeed, session, page = get_content(cookies)
                if not login_succeed:
                    cookies = None
                    print("[Error]")

                    if is_redirected_to_login_page(page):
                        print(
                            "Request failed. Try downloading the image directly "
                            "from https://developer.acconeer.com"
                        )

                else:
                    print("[OK]")

            if new_login:
                if _query_yes_no(
                    "\nWe use cookies to optimize the service of our applications."
                    "\n\nCookie Policy: https://acconeer.com/cookie-policy-eu/"
                    "\nPrivacy Statement: https://developer.acconeer.com/privacy-policy/"
                    "\n\nSelecting yes to the following question will store a cookie on "
                    "your computer:"
                    "\nRemember me?"
                ):
                    save_cookies(cookies)

            with tempfile.TemporaryDirectory() as tmp_dir:
                print("Preparing license agreement... ", end="", flush=True)
                license = DevLicense()
                license.load()
                print("[OK]")

                time.sleep(1)
                DevLicenseTuiDialog.run(log="textual.log", license=license)
                license_accepted = DevLicenseTuiDialog.get_accept()

                if license_accepted:
                    try:
                        print("Downloading image file... ", end="", flush=True)
                        bin_path, version = download(
                            session=session,
                            cookies=cookies,
                            page=page,
                            path=tmp_dir,
                            device=device,
                        )
                        print(f"[OK] (version: {version})")

                        try:
                            if _query_yes_no("Proceed to flashing you device?"):
                                print("Flashing...")
                                flash_image(bin_path, flash_port)
                        except ValueError:
                            print("No devices found, try connecting a device before flashing.")
                    except Exception as e:
                        print("[Error]")
                        log.error(str(e))
                else:
                    print("You need to accept the license agreement to download the image file.")

            session.close()

        except Exception as e:
            print(str(e))

    elif args.image:
        flash_port = find_flash_port(args.port)
        flash_image(args.image, flash_port)
    elif not args.clear:
        print("No image file selected!\n")
        parser.print_help()
