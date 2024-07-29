# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import functools
import operator
from typing import Optional

import serial

from acconeer.exptool.flash._device_flasher_base import DeviceFlasherBase
from acconeer.exptool.flash._stm32uart._meta import DEVICE_NAME_TO_ID


STM32_DEFAULT_BAUDRATE = 115200
STM32_UART_TIMEOUT = 2

FLASH_ADDRESS = 0x08000000

DFU_BOOT_DESCRIPTION = {
    "XM125": (
        "<p>"
        "<ol>"
        "<li>Press and hold the <b>DFU</b> button on the board</li>"
        "<li>Press the <b>RESET</b> button (still holding the DFU button)</li>"
        "<li>Release the <b>RESET</b> button</li>"
        "<li>Release the <b>DFU</b> button</li>"
        "</ol>"
        "</p>"
    ),
}


class Stm32DeviceException(Exception):
    pass


class Stm32FlashException(Exception):
    pass


class Stm32UartFlasher(DeviceFlasherBase):
    @staticmethod
    def flash(serial_device, device_name, image_path, progress_callback=None):
        if device_name not in DEVICE_NAME_TO_ID:
            msg = f"Unknown device '{device_name}'"
            raise Stm32DeviceException(msg)

        device_chip_id = DEVICE_NAME_TO_ID[device_name]

        flasher = Stm32FlashProtocol(serial_device.port)
        flasher.sync()
        chip_id = flasher.get_id()
        if chip_id != device_chip_id:
            msg = f"Incorrect STM32 chip_id 0x{chip_id:x}"
            raise Stm32DeviceException(msg)

        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            flasher.extended_erase()
            flasher.write_image(image_data, FLASH_ADDRESS, progress_callback=progress_callback)
            flasher.go(FLASH_ADDRESS)

        flasher.close()

    @staticmethod
    def get_boot_description(device_name: str) -> Optional[str]:
        description = (
            "Please visit https://developer.acconeer.com to find the latest flash "
            f"instructions for {device_name}."
        )

        if device_name in DFU_BOOT_DESCRIPTION:
            description = (
                f"<p>To flash the {device_name} it needs to be put in bootloader mode:</p>"
                f"{DFU_BOOT_DESCRIPTION[device_name]}"
            )

        return description


class Stm32FlashProtocol:
    ACK = 0x79
    NACK = 0x1F

    def __init__(self, port):
        self._port = port
        self._uart = UartComm(self._port)

    def close(self):
        if self._uart is not None:
            self._uart.close()
            self._uart = None

    def _wait_for_ack_or_nack(self):
        reply_array = self._uart.read(length=1)
        if len(reply_array) > 0:
            reply = reply_array[0]
            if reply in [self.ACK, self.NACK]:
                return reply
            else:
                msg = f"Unknown reply from STM32 bootloader [0x{reply:x}]"
                raise Stm32FlashException(msg)
        msg = "Device did not reply any data"
        raise Stm32FlashException(msg)

    def _wait_for_ack(self):
        reply = self._wait_for_ack_or_nack()
        if reply == self.NACK:
            msg = "Device replied NACK to command"
            raise Stm32FlashException(msg)

    def _command(self, cmd_byte):
        cmd_xor_byte = cmd_byte ^ 0xFF
        cmd = bytearray([cmd_byte, cmd_xor_byte])
        self._uart.write(cmd)
        self._wait_for_ack()

    def _read_bytes(self, length):
        byte_array = self._uart.read(length=length)
        if len(byte_array) != length:
            Stm32FlashException("Device did not reply correct amount of data")
        return byte_array

    def _checksum(self, array):
        return functools.reduce(operator.xor, array, 0)

    def _send_address(self, address):
        data_bytes = bytearray(address.to_bytes(length=4, byteorder="big"))
        checksum = self._checksum(data_bytes)
        data_bytes.append(checksum)
        self._uart.write(data_bytes)
        self._wait_for_ack()

    def _send_data(self, data_bytes):
        tx_data = bytearray([len(data_bytes) - 1])
        tx_data.extend(data_bytes)
        checksum = self._checksum(tx_data)
        tx_data.append(checksum)
        self._uart.write(tx_data)
        self._wait_for_ack()

    def _write_memory(self, address, byte_array):
        WRITE_MEMORY = 0x31

        if len(byte_array) > 256:
            Stm32FlashException("Memory chunk to large")

        while (len(byte_array) % 4) != 0:
            byte_array.extend(0xFF)

        self._command(WRITE_MEMORY)
        self._send_address(address)
        self._send_data(byte_array)

    def sync(self):
        CMD_SYNC = bytearray([0x7F])
        # Try so SYNC twice before failing
        for _ in range(0, 2):
            try:
                self._uart.write(CMD_SYNC)
                self._wait_for_ack_or_nack()
                return
            except Stm32FlashException:
                pass
        msg = f"DFU synchronization failed for '{self._port}', make sure device is in DFU mode"
        raise Stm32FlashException(msg)

    def get_id(self):
        GET_ID = 0x02
        self._command(GET_ID)
        len_bytes = self._read_bytes(1)
        len = int.from_bytes(len_bytes, byteorder="big")
        id_bytes = self._read_bytes(len + 1)
        id = int.from_bytes(id_bytes, byteorder="big")
        self._wait_for_ack()
        return id

    def extended_erase(self):
        EXTENDED_ERASE = 0x44
        self._command(EXTENDED_ERASE)
        self._uart.write([0xFF, 0xFF, 0x00])
        self._wait_for_ack()

    def write_image(self, byte_array, flash_address, progress_callback=None):
        MAX_CHUNK_SIZE = 256

        for pos in range(0, len(byte_array), MAX_CHUNK_SIZE):
            if progress_callback is not None:
                progress_callback(int(100 * pos / len(byte_array)))

            chunk_len = min(MAX_CHUNK_SIZE, len(byte_array) - pos)
            chunk_array = bytearray(byte_array[pos : pos + chunk_len])

            self._write_memory(flash_address + pos, chunk_array)

        if progress_callback is not None:
            progress_callback(100, True)

    def go(self, address):
        GO = 0x21

        self._command(GO)
        self._send_address(address)


class UartComm:
    def __init__(self, port):
        self._ser = serial.Serial(
            port=port,
            baudrate=STM32_DEFAULT_BAUDRATE,
            parity="E",
            rtscts=False,
            timeout=STM32_UART_TIMEOUT,
        )
        self._ser.reset_input_buffer()

    def close(self):
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def write(self, data):
        self._ser.write(data)

    def read(self, length=1):
        return bytearray(self._ser.read(length))
