# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

import base64
import hashlib
from enum import Enum
from struct import pack, unpack_from
from typing import Any, Callable, Dict, List, Optional, Tuple

import cbor2
import serial

from acconeer.exptool._core.communication.comm_devices import SerialDevice
from acconeer.exptool.flash._device_flasher_base import DeviceFlasherBase


MCUMGR_DEFAULT_BAUDRATE = 115200
MCUMGR_UART_TIMEOUT = 2

DFU_BOOT_DESCRIPTION = {
    "XM126": (
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


class McuMgrFlashException(Exception):
    pass


class McuMgrUartFlasher(DeviceFlasherBase):
    def flash(
        self,
        serial_device: SerialDevice,
        device_name: str,
        image_path: str,
        progress_callback: Optional[Callable[[int, bool], None]] = None,
    ) -> None:
        flasher = McuMgrFlashProtocol(serial_device.port)

        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
            flasher.write_image(image_data, progress_callback=progress_callback)
            flasher.reset()

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


class NmpOp(Enum):
    READ = 0
    READ_RSP = 1
    WRITE = 2
    WRITE_RSP = 3


class NmpGroup(Enum):
    OS = 0
    IMAGE = 1
    STAT = 2
    CONFIG = 3
    LOG = 4
    CRASH = 5
    SPLIT = 6
    RUN = 7
    FS = 8
    PERUSER = 64


class NmpIdOs(Enum):
    ECHO = 0
    CONS_ECHO_CTRL = 1
    TASKSTAT = 2
    MPSTAT = 3
    DATETIME_STR = 4
    RESET = 5


class NmpIdImage(Enum):
    STATE = 0
    UPLOAD = 1
    FILE = 2
    CORELIST = 3
    CORELOAD = 4
    ERASE = 5


class NmPHeader:
    fmt = "!BBHHBB"
    size = 8

    def __init__(
        self,
        op: NmpOp,
        group: NmpGroup,
        id: Enum,
        length: int = 0,
        seq_id: int = 0,
        flags: int = 0,
    ):
        self.op = op
        self.group = group
        self.id = id
        self.flags = flags
        self.length = length
        self.seq_id = seq_id

    @staticmethod
    def decode(b: bytes) -> NmPHeader:
        t = unpack_from(NmPHeader.fmt, b)

        return NmPHeader(t[0], t[3], t[5], length=t[2], seq_id=t[4], flags=t[1])

    def encode(self) -> bytes:
        return pack(
            NmPHeader.fmt,
            self.op.value,
            self.flags,
            self.length,
            self.group.value,
            self.seq_id,
            self.id.value,
        )

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}(op:{self.op} group:{self.group} id:{self.id} "
            f"len:{self.length} seq:{self.seq_id} flags:{self.flags})"
        )


class ResetRequestHeader(NmPHeader):
    def __init__(self, length: int = 0, seq_id: int = 0, flags: int = 0):
        super().__init__(NmpOp.WRITE, NmpGroup.OS, NmpIdOs.RESET, length, seq_id, flags)


class ImageRequestHeader(NmPHeader):
    def __init__(self, length: int = 0, seq_id: int = 0, flags: int = 0):
        super().__init__(NmpOp.WRITE, NmpGroup.IMAGE, NmpIdImage.UPLOAD, length, seq_id, flags)


class ResetRequest:
    def __init__(self, seq_id: int = 0):
        self.seq_id = seq_id

    def encode(self) -> bytes:
        req_header = ResetRequestHeader(length=1, seq_id=self.seq_id)

        data = req_header.encode()

        # calculate CRC16 of it and append to the request
        crc = McuMgrFlashProtocol.calc_crc16_xmodem(0, data).to_bytes(2, byteorder="big")
        data += crc

        # prepend chunk length
        chunk_len = len(data).to_bytes(2, byteorder="big")
        data = chunk_len + data

        # convert to base64
        enc_data = base64.b64encode(data)

        # Prepend start designator and append newline to base64 encoded data
        return b"\x06\x09" + enc_data + b"\n"


class ResetResponse:
    @staticmethod
    def decode(data: bytes, seq_id: int) -> None:
        # decode header and check seq
        header = ResetRequestHeader.decode(data)

        if seq_id != header.seq_id:
            msg = f"Seq number mismatch: {header}"
            raise McuMgrFlashException(msg)

        if len(data) > ResetRequestHeader.size:
            dec_msg: Dict[str, Any] = cbor2.loads(data[ResetRequestHeader.size :])
        else:
            msg = f"Complete header w/o payload: {header}"
            raise McuMgrFlashException(msg)

        if "rc" not in dec_msg:
            msg = "Missing key 'rc' in response"
            raise McuMgrFlashException(msg)

        if dec_msg["rc"] != 0:
            msg = f"Error code: '{dec_msg['rc']}' response"
            raise McuMgrFlashException(msg)


class ImageUploadRequest:
    def __init__(
        self,
        image_num: int,
        offset: int,
        data_len: Optional[int],
        data: bytes,
        data_sha: Optional[bytes],
        seq_id: int,
    ):
        self.offset = offset
        self.data_len = data_len
        self.data = data
        self.seq_id = seq_id

        if data_sha is None and data_len is None:
            self.payload_dict: Dict[str, Any] = {
                "off": self.offset,
                "data": self.data,
            }
        else:
            self.payload_dict = {
                "off": self.offset,
                "data": self.data,
                "sha": data_sha,
                "len": self.data_len,
            }

    def encode(self, line_length: int = 128) -> Tuple[List[bytes], int]:
        """
        encodes self.payload_dict and header
        returns both as bytes
        """
        ret_data = []

        # convert to bytes with CBOR
        payload_bytes = cbor2.dumps(self.payload_dict)

        req_header = ImageRequestHeader(length=len(payload_bytes), seq_id=self.seq_id)

        data = req_header.encode() + payload_bytes

        # calculate CRC16 of it and append to the request
        crc = McuMgrFlashProtocol.calc_crc16_xmodem(0, data).to_bytes(2, byteorder="big")
        data += crc

        # prepend chunk length
        chunk_len = len(data).to_bytes(2, byteorder="big")
        data = chunk_len + data

        # convert to base64
        enc_data = base64.b64encode(data)

        written = 0
        total_len = len(enc_data)

        # transfer in blocks of max line_length bytes per line
        while written < total_len:
            # start designator
            if written == 0:
                out_data = b"\x06\x09"
            else:
                out_data = b"\x04\x14"

            write_len = min(line_length - 4, total_len - written)
            out_data = out_data + enc_data[written : written + write_len] + b"\n"

            written = written + write_len

            ret_data.append(out_data)

        return ret_data, total_len

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(dict:{self.payload_dict}"


class ImageUploadResponse:
    @staticmethod
    def decode(data: bytes, seq_id: int) -> int:
        # decode header and check seq
        header = ImageRequestHeader.decode(data)

        if seq_id != header.seq_id:
            msg = f"Seq number mismatch: {header}"
            raise McuMgrFlashException(msg)

        if len(data) > ImageRequestHeader.size:
            dec_msg: Dict[str, Any] = cbor2.loads(data[ImageRequestHeader.size :])
        else:
            msg = f"Complete header w/o payload: {header}"
            raise McuMgrFlashException(msg)

        if "rc" not in dec_msg:
            msg = "Missing key 'rc' in response"
            raise McuMgrFlashException(msg)

        if dec_msg["rc"] != 0:
            msg = f"Error code: '{dec_msg['rc']}' response"
            raise McuMgrFlashException(msg)

        if "off" not in dec_msg:
            msg = "Missing key 'off' in response"
            raise McuMgrFlashException(msg)

        return int(dec_msg["off"])


class McuMgrFlashProtocol:
    mtu = 512
    slot = 0

    def __init__(self, port: str):
        self._port = port
        self._uart: Optional[UartComm] = UartComm(self._port)
        self.seq_id = 0

    def close(self) -> None:
        if self._uart is not None:
            self._uart.close()
            self._uart = None

    @staticmethod
    def calc_crc16_xmodem(seed: int, data: bytes) -> int:
        for byte in data:
            seed = ((seed >> 8) | (seed << 8)) & 0xFFFF
            seed ^= byte
            seed ^= ((seed & 0xFF) >> 4) & 0xFFFF
            seed ^= (seed << 12) & 0xFFFF
            seed ^= ((seed & 0xFF) << 5) & 0xFFFF

        return seed

    def get_next_seq_id(self) -> int:
        seq_id = self.seq_id
        self.seq_id = (self.seq_id + 1) % 256

        return seq_id

    def decode_response(self) -> bytes:
        assert self._uart is not None

        bytes_read = 0
        result = b""
        expected_len = 0

        while True:
            rec_data = self._uart.read(2)

            # chunk start marker expected
            if bytes_read == 0:
                if rec_data != b"\x06\x09":
                    msg = "Incorrect start marker"
                    raise McuMgrFlashException(msg)
            else:
                if rec_data != b"\x04\x14":
                    msg = "Incorrect start marker"
                    raise McuMgrFlashException(msg)

            # read until newline
            while True:
                b = self._uart.read(1)

                if b == b"\x0a":
                    break
                else:
                    result += b
                    bytes_read += 1

            dec_data = base64.b64decode(result)

            if expected_len == 0:
                length = int.from_bytes(dec_data[:2], byteorder="big")
                if length > 0:
                    expected_len = length

            # stop when done
            if len(dec_data) >= expected_len:
                break

        # decode base64
        decoded = base64.b64decode(result)

        # verify length: must be the decoded length, minus the 2 bytes to encode the length
        length = int.from_bytes(decoded[:2], byteorder="big")

        if length != len(decoded) - 2:
            msg = "Wrong chunk length"
            raise McuMgrFlashException(msg)

        # verify checksum
        data = decoded[2 : len(decoded) - 2]
        read_crc = decoded[len(decoded) - 2 :]
        calculated_crc = McuMgrFlashProtocol.calc_crc16_xmodem(0, data).to_bytes(
            2, byteorder="big"
        )

        if read_crc != calculated_crc:
            msg = "Wrong crc"
            raise McuMgrFlashException(msg)

        return data

    def reset(self) -> None:
        assert self._uart is not None

        seq_id = self.get_next_seq_id()

        req = ResetRequest(seq_id=seq_id)
        self._uart.write(req.encode())

        decoded_data = self.decode_response()

        ResetResponse.decode(decoded_data, seq_id)

    def write_image(
        self, byte_array: bytes, progress_callback: Optional[Callable[[int, bool], None]] = None
    ) -> None:
        assert self._uart is not None

        offset = 0
        byte_array_len = len(byte_array)

        while True:
            offset_start = 0
            try_length = McuMgrFlashProtocol.mtu
            seq_id = self.get_next_seq_id()

            while True:
                image_num = McuMgrFlashProtocol.slot

                if offset + try_length > byte_array_len:
                    try_length = byte_array_len - offset

                chunk = byte_array[offset : offset + try_length]

                # Include SHA and total data length only in first ImageUploadRequest
                if offset == 0:
                    sha = hashlib.sha256(byte_array).digest()
                    data_len = byte_array_len
                else:
                    sha = None
                    data_len = None

                req = ImageUploadRequest(
                    image_num=image_num,
                    offset=offset,
                    data_len=data_len,
                    data=chunk,
                    data_sha=sha,
                    seq_id=seq_id,
                )

                enc_data, enc_data_len = req.encode()

                # Test if encoded data is larger than MTU
                if enc_data_len > McuMgrFlashProtocol.mtu:
                    reduce = enc_data_len - McuMgrFlashProtocol.mtu
                    if reduce > try_length:
                        msg = "MTU too small"
                        raise McuMgrFlashException(msg)

                    # number of bytes to reduce is base64 encoded, calculate back the number of bytes
                    # and then reduce a bit more for base64 filling and rounding
                    try_length -= int(reduce * 3 / 4 + 3)
                    continue

                # Send all frames
                for frame in enc_data:
                    self._uart.write(frame)

                decoded_data = self.decode_response()

                offset = ImageUploadResponse.decode(decoded_data, seq_id)
                break

            if offset_start == offset:
                msg = "Wrong offset received"
                raise McuMgrFlashException(msg)

            if progress_callback is not None:
                progress_callback(int(100 * offset / byte_array_len), False)

            if offset == byte_array_len:
                if progress_callback is not None:
                    progress_callback(100, True)
                break


class UartComm:
    def __init__(self, port: str):
        self._ser = serial.Serial(
            port=port,
            baudrate=MCUMGR_DEFAULT_BAUDRATE,
            parity="N",
            rtscts=False,
            timeout=MCUMGR_UART_TIMEOUT,
        )
        self._ser.reset_input_buffer()

    def close(self) -> None:
        if self._ser is not None:
            self._ser.close()
            self._ser = None

    def write(self, data: bytes) -> None:
        self._ser.write(data)

    def read(self, length: int = 1) -> bytearray:
        return bytearray(self._ser.read(length))
