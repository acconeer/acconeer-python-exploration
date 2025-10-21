# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

"""Tool dfu/flash devices with bootloader firmware"""

import logging
import time

import serial
from serial.serialutil import SerialException
from serial.tools import list_ports

from acconeer.exptool._core.communication.comm_devices import get_usb_devices
from acconeer.exptool._core.communication.links.usb_link import PyUsbCdc
from acconeer.exptool.flash._device_flasher_base import DeviceFlasherBase
from acconeer.exptool.flash._flash_exception import FlashException

from ._bootloader_comm import BLCommunication, CommandFailed


log = logging.getLogger(__name__)


class ImageFlasher:
    """A class that handles image flashing"""

    def __init__(self, serial_dev):
        self._ser = serial_dev
        self._comm = BLCommunication(self._ser)
        self._progress_callback = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.reset_and_close()

    def reset_and_close(self):
        """reset system and close communication channel"""
        if self._comm is not None:
            self._comm.reset()

        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def set_progress_callback(self, progress_callback):
        self._progress_callback = progress_callback

    def erase_image(self, erase_size):
        """erase image"""
        if not self._comm.is_image_erased(erase_size):
            log.debug("-Flash not erased, erasing...")
            self._comm.image_erase(erase_size)
        else:
            log.debug("-Flash already erased")

    def flash_image_bytearray(self, image_data):
        """flash image byte array to bootloader board"""

        image_size = len(image_data)
        self.erase_image(image_size)

        max_chunk_size = 32768
        offset = 0
        while offset < image_size:
            chunk_size = min(image_size - offset, max_chunk_size)
            chunk_array = image_data[offset : offset + chunk_size]
            log.debug(
                f"\r-Flashing: Writing {chunk_size} bytes to offset {offset}                ",
            )
            if self._progress_callback is not None:
                self._progress_callback(int(100 * offset / image_size))
            self._comm.image_write_block(offset, chunk_array)
            offset += chunk_size
        if self._progress_callback is not None:
            self._progress_callback(100, True)

        log.debug("Flashed Image:")
        log.debug(f" - Name:    {self._comm.get_app_sw_name()}")
        log.debug(f" - Version: {self._comm.get_app_sw_version()}")

    def flash_image_file(self, image_name):
        """flash image file to bootloader board"""

        with open(image_name, "rb") as image_file:
            image_data = image_file.read()
            self.flash_image_bytearray(image_data)


class BootloaderTool(DeviceFlasherBase):
    """Class to handle dfu/flash of devices with bootloader firmware"""

    """
    Class to handle dfu/flash of devices with bootloader firmware

    Args:
    device_vid          - The USB vendor ID of the product(s)
    bootloader_pid      - The USB product ID of the product bootloader
    """

    def __init__(self, *, device_vid, bootloader_pid, is_usb=True):
        super().__init__()
        self.device_vid = device_vid
        self.bootloader_pid = bootloader_pid
        self.is_usb = is_usb

    @staticmethod
    def _find_port(search_vid, search_pid, search_port=None):
        all_ports = list_ports.comports()
        found_ports = [
            port for port in all_ports if port.vid == search_vid and port.pid == search_pid
        ]

        if len(found_ports) > 1 and search_port is not None:
            found_ports = [port for port in all_ports if port.device == search_port]
            if len(found_ports) < 1:
                msg = "Couldn't find a device on the specified port"
                raise FlashException(msg)
            return found_ports[0].device
        elif len(found_ports) > 0:
            return found_ports[0].device

        return None

    @staticmethod
    def _find_usb_device(search_port):
        try:
            usb_devices = get_usb_devices()
            if search_port in usb_devices:
                return search_port
        except ImportError:
            return None

    @staticmethod
    def _find_usb_dfu_device():
        try:
            usb_devices = get_usb_devices()
            for dev in usb_devices:
                if dev.unflashed:
                    return dev
            return None
        except ImportError:
            return None

    @staticmethod
    def _is_usb_dfu_device(device_port):
        usb_device = BootloaderTool._find_usb_device(device_port)
        return usb_device is not None and usb_device.unflashed

    def enter_dfu(self, device_port):
        """Function to make the devices enter Bootloader/DFU mode"""

        cdc_port = BootloaderTool._find_port(self.device_vid, self.bootloader_pid, device_port)

        if cdc_port is not None or BootloaderTool._is_usb_dfu_device(device_port):
            log.debug("Device already in DFU mode")
        else:
            log.debug("Reset to DFU mode")
            exploration_server_usb_device = BootloaderTool._find_usb_device(device_port)

            if exploration_server_usb_device:
                log.debug("Exploration server active, enter DFU mode")
                ser = PyUsbCdc(
                    vid=exploration_server_usb_device.vid,
                    pid=exploration_server_usb_device.pid,
                )
                ser.send_break()
                time.sleep(0.1)
                ser.write(bytes('{ "cmd": "stop_application" }\n', "utf-8"))
                ser.close()

            else:
                msg = "Device not found"
                raise FlashException(msg)

            # Wait for DFU device to appear
            retries = 5
            device_found = False
            cdc_port = None
            while retries > 0:
                log.debug("Wait for DFU device...")
                time.sleep(1)
                cdc_port = BootloaderTool._find_port(
                    self.device_vid, self.bootloader_pid, device_port
                )
                usb_dfu = BootloaderTool._find_usb_dfu_device()
                if cdc_port is not None or usb_dfu is not None:
                    device_found = True
                    break
                retries -= 1

            if not device_found:
                msg = "DFU device not found"
                raise FlashException(msg)

    @staticmethod
    def _try_open_port(serial_port):
        retries = 5
        ser = None
        while retries > 0 and ser is None:
            try:
                ser = serial.Serial(serial_port, exclusive=True)
            except SerialException:
                ser = None
                time.sleep(0.2)
                retries -= 1

        if ser is None:
            msg = f"Flash failed, {serial_port} cannot be opened"
            raise FlashException(msg)

        return ser

    def flash(self, device_port, device_name, image_path, progress_callback=None):
        """Flash an firmware image to the device"""
        self.enter_dfu(device_port)
        dfu_port = self._find_port(self.device_vid, self.bootloader_pid, device_port)
        serial_dev = None
        if dfu_port is not None:
            serial_dev = self._try_open_port(dfu_port)
        else:
            msg = "Flash failed, device not found"
            raise FlashException(msg)

        try:
            with ImageFlasher(serial_dev) as image_flasher:
                image_flasher.set_progress_callback(progress_callback)
                image_flasher.flash_image_file(image_path)
        except CommandFailed as exc:
            if "Data does not contain a valid image" in str(exc):
                error_string = (
                    f"ERROR: The selected file does not contain a valid image for {device_name}"
                )
            else:
                error_string = f"ERROR: {str(exc)}"
            raise FlashException(error_string)
