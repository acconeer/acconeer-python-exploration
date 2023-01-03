# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

""" Tool dfu/flash devices with bootloader firmware """

import logging
import time

import serial
from serial.serialutil import SerialException
from serial.tools import list_ports

from acconeer.exptool._pyusb.pyusbcomm import PyUsbCdc
from acconeer.exptool.flash._device_flasher_base import DeviceFlasherBase
from acconeer.exptool.flash._xc120._bootloader_comm import BLCommunication
from acconeer.exptool.flash._xc120._meta import (
    ACCONEER_VID,
    ACCONEER_XC120_BOOTLOADER_PID,
    ACCONEER_XC120_EXPLORATION_SERVER_PID,
)
from acconeer.exptool.utils import get_usb_devices


try:
    from acconeer.exptool._winusbcdc.usb_cdc import ComPort
except ImportError:
    ComPort = None


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

    @staticmethod
    def _find_port(search_vid, search_pid, search_port=None):
        all_ports = list_ports.comports()
        found_ports = [
            port for port in all_ports if port.vid == search_vid and port.pid == search_pid
        ]

        if len(found_ports) > 1 and search_port is not None:
            found_ports = [port for port in all_ports if port.device == search_port]
            if len(found_ports) < 1:
                raise Exception("Couldn't find a device on the specified port")
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
    def _try_open_port(device_port):
        retries = 5
        port_ok = False
        while retries > 0:
            time.sleep(0.2)
            try:
                ser = serial.Serial(device_port, exclusive=True)
                ser.close()
                port_ok = True
                break
            except SerialException:
                retries -= 1

        if not port_ok:
            raise ValueError(f"Device port {device_port} cannot be opened")

    @staticmethod
    def _is_usb_dfu_device(device_port):
        usb_device = BootloaderTool._find_usb_device(device_port)
        return usb_device is not None and usb_device.unflashed

    @staticmethod
    def enter_dfu(device_port):
        """Function to make the devices enter Bootloader/DFU mode"""

        cdc_port = BootloaderTool._find_port(
            ACCONEER_VID, ACCONEER_XC120_BOOTLOADER_PID, device_port
        )

        BootloaderTool._try_open_port(cdc_port)

        if cdc_port is not None or BootloaderTool._is_usb_dfu_device(device_port):
            log.debug("Device already in DFU mode")
        else:
            log.debug("Reset to DFU mode")
            exploration_server_port = BootloaderTool._find_port(
                ACCONEER_VID,
                ACCONEER_XC120_EXPLORATION_SERVER_PID,
                device_port,
            )
            exploration_server_usb_device = BootloaderTool._find_usb_device(device_port)

            if exploration_server_port or exploration_server_usb_device:
                log.debug("Exploration server active, enter DFU mode")
                if exploration_server_port:
                    BootloaderTool._try_open_port(exploration_server_port)
                    ser = serial.Serial(exploration_server_port, exclusive=True)
                else:
                    if ComPort is not None:
                        ser = ComPort(
                            vid=exploration_server_usb_device.vid,
                            pid=exploration_server_usb_device.pid,
                        )
                    else:
                        ser = PyUsbCdc(
                            vid=exploration_server_usb_device.vid,
                            pid=exploration_server_usb_device.pid,
                        )
                ser.send_break()
                time.sleep(0.1)
                ser.write(bytes('{ "cmd": "stop_application" }\n', "utf-8"))
                ser.close()

            else:
                raise ValueError("Device not found")

            # Wait for DFU device to appear
            retries = 5
            device_found = False
            cdc_port = None
            while retries > 0:
                log.debug("Wait for DFU device...")
                time.sleep(1)
                cdc_port = BootloaderTool._find_port(
                    ACCONEER_VID, ACCONEER_XC120_BOOTLOADER_PID, device_port
                )
                usb_dfu = BootloaderTool._find_usb_dfu_device()
                if cdc_port is not None or usb_dfu is not None:
                    device_found = True
                    break
                retries -= 1

            if not device_found:
                raise ValueError("DFU device not found")

    @staticmethod
    def flash(device_port, device_name, image_path, progress_callback=None):
        """Flash an firmware image to the device"""
        BootloaderTool.enter_dfu(device_port)
        dfu_port = BootloaderTool._find_port(
            ACCONEER_VID, ACCONEER_XC120_BOOTLOADER_PID, device_port
        )
        usb_dfu = BootloaderTool._find_usb_dfu_device()
        serial_dev = None
        if dfu_port is not None:
            serial_dev = serial.Serial(dfu_port, exclusive=True)
        elif usb_dfu is not None and ComPort is not None:
            serial_dev = ComPort(
                vid=usb_dfu.vid,
                pid=usb_dfu.pid,
            )
        else:
            raise ValueError("Flash failed, device not found")

        with ImageFlasher(serial_dev) as image_flasher:
            image_flasher.set_progress_callback(progress_callback)
            image_flasher.flash_image_file(image_path)

    @staticmethod
    def erase(device_port):
        """Erase application image from device"""
        BootloaderTool.enter_dfu(device_port)
        dfu_port = BootloaderTool._find_port(
            ACCONEER_VID, ACCONEER_XC120_BOOTLOADER_PID, device_port
        )
        BootloaderTool._try_open_port(dfu_port)
        with ImageFlasher(dfu_port) as image_flasher:
            image_flasher.erase_image(1024)  # It is enough to erase the header
