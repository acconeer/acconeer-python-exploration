# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import argparse
import getpass
import re
import tempfile
import time
import typing as t

from acconeer.exptool._artifact_repository import (
    ArtifactRepository,
    ArtifactRepositoryError,
    DevSiteRepository,
    LoginRequiredError,
    create_artifact_repository,
    load_plugin_file,
)
from acconeer.exptool._core.communication import comm_devices
from acconeer.exptool._core.communication.links.usb_link import UsbPortError
from acconeer.exptool._dev_license import DevLicense
from acconeer.exptool.flash._bootloader_tool import BootloaderTool
from acconeer.exptool.flash._flash_exception import FlashException
from acconeer.exptool.flash._products import (
    EVK_TO_PRODUCT_MAP,
    PRODUCT_NAME_TO_ARTIFACT,
    PRODUCT_NAME_TO_FLASH_MAP,
    PRODUCT_PID_TO_FLASH_MAP,
)

from ._dev_license_tui import DevLicenseTuiDialog


BIN_FETCH_PROMPT = (
    "To fetch the latest image you need to log into your Acconeer Developer account.\n\n"
    "If you don't have an account you can create one here:\n"
    "https://developer.acconeer.com/create-account/ \n\n"
    "Lost your password? Recover it here:\n"
    "https://developer.acconeer.com/recover-password/"
)


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
        raise FlashException("invalid default answer: '%s'" % default)

    while True:
        print(question + prompt, end="", flush=True)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def _flasher_progress_callback(progress: int, end: bool = False) -> None:
    print(f"\rProgress: [{progress}/100]", end="", flush=True)
    if end:
        print()


def flash_image(
    image_path: str,
    flash_device: comm_devices.CommDevice,
    device_name: str,
    progress_callback: t.Callable[[int, bool], t.Any] = lambda *_: None,
) -> None:
    if flash_device:
        serial_device_name = device_name or flash_device.name
        if serial_device_name is None:
            msg = "Unknown device type"
            raise FlashException(msg)
        serial_device_name = serial_device_name.upper()

        if (
            isinstance(flash_device, comm_devices.USBDevice)
            and flash_device.pid in PRODUCT_PID_TO_FLASH_MAP
        ):
            bootloader = PRODUCT_PID_TO_FLASH_MAP[flash_device.pid]()
            bootloader.flash(
                flash_device, serial_device_name, image_path, progress_callback=progress_callback
            )
        elif (
            isinstance(flash_device, comm_devices.SerialDevice)
            and serial_device_name in PRODUCT_NAME_TO_FLASH_MAP
        ):
            bootloader = PRODUCT_NAME_TO_FLASH_MAP[serial_device_name]()
            bootloader.flash(flash_device, serial_device_name, image_path, progress_callback)
        else:
            msg = f"No flash support device {str(flash_device)}"
            raise FlashException(msg)
    else:
        msg = "No devices found, try connecting a device before flashing."
        raise FlashException(msg)


def _is_usb_device(name: str) -> bool:
    return issubclass(PRODUCT_NAME_TO_FLASH_MAP[name], BootloaderTool)


def _get_flash_device_from_args(
    args: argparse.Namespace,
) -> t.Union[comm_devices.SerialDevice, comm_devices.USBDevice]:
    device_name: str = args.device
    port = args.port if hasattr(args, "port") else None
    serial_number = args.serial_number if hasattr(args, "serial_number") else None
    flash_device: t.Optional[t.Union[comm_devices.SerialDevice, comm_devices.USBDevice]] = None

    if device_name == "XM125":
        device_name = "XE125"
    elif device_name == "XM126":
        device_name = "XB122"

    # Handle serial port devices
    if not _is_usb_device(device_name):
        flash_device = None
        for serial_device in comm_devices.get_serial_devices():
            if isinstance(serial_device, comm_devices.SerialDevice) and port == serial_device.port:
                flash_device = serial_device
                break
        if flash_device is None:
            msg = f"Port '{port}' could not be found\n"
            raise FlashException(msg)
        return flash_device

    # Handle USB devices
    found_usb_devices = []
    for usb_device in comm_devices.get_usb_devices():
        if device_name is not None and usb_device.name != device_name:
            # Device name did not match
            continue
        elif serial_number is not None and usb_device.serial != serial_number:
            # Serial number did not match
            continue
        else:
            found_usb_devices.append(usb_device)

    if len(found_usb_devices) == 0:
        # Handle Serial Port USB devices (Bootloader)
        flash_device = None
        for serial_device in comm_devices.get_serial_devices():
            if serial_device.name == device_name:
                return serial_device

        if serial_number is not None:
            msg = f"No {device_name} device with serial={serial_number} could be found\n"
        else:
            msg = f"No {device_name} device could be found\n"
        raise FlashException(msg)
    elif len(found_usb_devices) > 1:
        print(f"Found multiple {device_name} devices:")
        print("".join([f" - {dev}\n" for dev in found_usb_devices]))
        msg = "Use --serial-number to select device to be flashed"
        raise FlashException(msg)

    flash_device = found_usb_devices[0]
    print(f"Flashing {flash_device}")

    return flash_device


def get_flash_known_devices() -> list[str]:
    known_devices = []
    for _, item in EVK_TO_PRODUCT_MAP.items():
        if item not in known_devices:
            known_devices.append(item)
    return known_devices


def get_flash_download_name(device: comm_devices.CommDevice, device_name: t.Optional[str]) -> str:
    name = device_name or device.name
    if name in EVK_TO_PRODUCT_MAP:
        return EVK_TO_PRODUCT_MAP[name]
    msg = f"Unknown device {name}"
    raise FlashException(msg)


def get_boot_description(
    flash_device: comm_devices.CommDevice,
    device_name: str,
) -> t.Optional[str]:
    flash_device_name = device_name or flash_device.name
    product = None

    if flash_device_name in EVK_TO_PRODUCT_MAP:
        product = EVK_TO_PRODUCT_MAP[flash_device_name]

    if product in PRODUCT_NAME_TO_FLASH_MAP:
        return PRODUCT_NAME_TO_FLASH_MAP[product].get_boot_description(product)

    return None


def get_post_dfu_description(
    flash_device: comm_devices.CommDevice,
    device_name: str,
) -> t.Optional[str]:
    flash_device_name = device_name or flash_device.name
    product = None

    if flash_device_name in EVK_TO_PRODUCT_MAP:
        product = EVK_TO_PRODUCT_MAP[flash_device_name]

    if product in PRODUCT_NAME_TO_FLASH_MAP:
        return PRODUCT_NAME_TO_FLASH_MAP[product].get_post_dfu_description(product)

    return None


def is_fw_downloadable(device_name: str) -> bool:
    device_name_upper = device_name.upper()
    if device_name_upper in EVK_TO_PRODUCT_MAP:
        return EVK_TO_PRODUCT_MAP[device_name_upper] in PRODUCT_NAME_TO_ARTIFACT
    return False


def _fetch_and_flash(args: argparse.Namespace) -> None:
    flash_device = _get_flash_device_from_args(args)

    if args.artifact_repository is not None:
        load_plugin_file(args.artifact_repository)
    devsite: ArtifactRepository = create_artifact_repository()
    remember_me = False
    asked_to_remember_me = False

    def _ensure_logged_in() -> None:
        nonlocal remember_me, asked_to_remember_me

        print("\nLogging in... ", end="", flush=True)
        print("[OK]" if devsite.has_logged_in_previously() else "[Error]")

        while not devsite.has_logged_in_previously():
            print("\n" + BIN_FETCH_PROMPT)
            email = input("\nEmail: ")
            password = getpass.getpass("Password: ")
            if not asked_to_remember_me:
                remember_me = _query_yes_no(
                    "\nWe use cookies to optimize the service of our applications."
                    "\n\nCookie Policy: https://acconeer.com/cookie-policy-eu/"
                    "\nPrivacy Statement: https://developer.acconeer.com/privacy-policy/"
                    "\n\nSelecting yes to the following question will store a cookie on "
                    "your computer:"
                    "\nRemember me?"
                )
                asked_to_remember_me = True
            devsite.login(email, password, remember_me=remember_me)

            print("\nLogging in... ", end="", flush=True)
            if not devsite.has_logged_in_previously():
                print("[Error]")
                print(
                    "Request failed. Try downloading the image directly "
                    "from https://developer.acconeer.com"
                )
            else:
                print("[OK]")

    _ensure_logged_in()

    with tempfile.TemporaryDirectory() as tmp_dir:
        print("Preparing license agreement... ", end="", flush=True)
        license = DevLicense()
        license.load()
        print("[OK]")

        time.sleep(1)
        DevLicenseTuiDialog.run(log="textual.log", license=license)
        license_accepted = DevLicenseTuiDialog.get_accept()

        if license_accepted:
            device_name = get_flash_download_name(flash_device, args.device)
            print(f"Downloading {device_name} image file... ", end="", flush=True)
            try:
                bin_path, version = devsite.download(
                    artifact=PRODUCT_NAME_TO_ARTIFACT[device_name],
                    path=tmp_dir,
                )
            except LoginRequiredError:
                print("[Error] Cookies have gone stale, please log in again.")
                devsite.forget_login()
                _ensure_logged_in()
                bin_path, version = devsite.download(
                    artifact=PRODUCT_NAME_TO_ARTIFACT[device_name],
                    path=tmp_dir,
                )
            print(f"[OK] (version: {version})")

            boot_description = get_boot_description(flash_device, device_name)
            if boot_description:
                boot_description = re.sub("<li>", " - ", boot_description)
                boot_description = re.sub("</[p|li]+?>", "\n", boot_description)
                boot_description = re.sub("<[^<]+?>", "", boot_description)
                print("\n\n" + boot_description)
            if _query_yes_no("Proceed to flashing you device?"):
                print("Flashing...")
                flash_image(
                    bin_path,
                    flash_device,
                    device_name=device_name,
                    progress_callback=_flasher_progress_callback,
                )
            post_dfu_description = get_post_dfu_description(flash_device, device_name)
            if post_dfu_description:
                post_dfu_description = re.sub("<li>", " - ", post_dfu_description)
                post_dfu_description = re.sub("</[p|li]+?>", "\n", post_dfu_description)
                post_dfu_description = re.sub("<[^<]+?>", "", post_dfu_description)
                print("\n\n" + post_dfu_description)
        else:
            print("You need to accept the license agreement to download the image file.")


def _flash(args: argparse.Namespace) -> None:
    flash_device = _get_flash_device_from_args(args)
    flash_image(
        args.image,
        flash_device,
        device_name=args.device,
        progress_callback=_flasher_progress_callback,
    )


def _add_common_options(parser: argparse.ArgumentParser) -> None:
    image_group = parser.add_mutually_exclusive_group(required=True)
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
    # A pluggy plugin file providing the repository '--fetch' gets the image
    # from, instead of the developer site. Internal use only.
    parser.add_argument(
        "--artifact-repository",
        dest="artifact_repository",
        help=argparse.SUPPRESS,  # makes option hidden
    )


def _add_usb_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--serial-number",
        "-s",
        dest="serial_number",
        help="Device serial number. Only needed if multiple devices are connected.",
        type=str,
    )
    _add_common_options(parser)


def _add_serial_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--port",
        "-p",
        dest="port",
        help="Serial port",
        type=str,
        required=True,
    )
    _add_common_options(parser)


def main() -> None:
    parser = argparse.ArgumentParser(description="Image Flasher")
    parser.prog = "python -m acconeer.exptool.flash"
    action_subparsers = parser.add_subparsers(
        help="sub-command help", dest="operation", required=True
    )
    action_subparsers.add_parser("list", help="List connected devices")
    action_subparsers.add_parser("clear", help="Clears saved login session")
    flash_subparser = action_subparsers.add_parser("flash", help="Flash device")
    device_subparsers = flash_subparser.add_subparsers(
        help="sub-command help", dest="device", required=True
    )

    for key in PRODUCT_NAME_TO_FLASH_MAP:
        if _is_usb_device(key):
            usb_subparser = device_subparsers.add_parser(key, help=f"Flash {key} device")
            _add_usb_options(usb_subparser)
        else:
            serial_subparser = device_subparsers.add_parser(key, help=f"Flash {key} device")
            _add_serial_options(serial_subparser)

    args = parser.parse_args()

    if args.operation == "list":
        usb_devices = comm_devices.get_usb_devices()
        serial_devices = comm_devices.get_serial_devices()
        if not usb_devices and not serial_devices:
            print("No devices available")
        else:
            if usb_devices:
                print("== USB Devices ==")
                print("".join([f" - {dev}\n" for dev in usb_devices]))
            if serial_devices:
                print("== Serial Devices ==")
                print("".join([f" - {dev}\n" for dev in serial_devices]))
        return
    elif args.operation == "clear":
        DevSiteRepository(cookies=None).forget_login()
        print("Saved login session cookie deleted!\n")
    elif args.operation == "flash":
        try:
            if args.fetch:
                if is_fw_downloadable(args.device):
                    _fetch_and_flash(args)
                else:
                    print(f"The image file for {args.device} is not available for download")
            elif args.image:
                _flash(args)
        except FlashException as e:
            print(f"\n{str(e)}\n")
        except UsbPortError as e:
            print(f"\n{str(e)}\n")
        except ArtifactRepositoryError as e:
            print(f"\n{str(e)}\n")
