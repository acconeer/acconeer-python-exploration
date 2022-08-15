# Copyright (c) Acconeer AB, 2022
# All rights reserved

import ctypes
import ctypes.util
import enum
import os
import platform
from ctypes import POINTER, byref
from glob import glob


C_PVOID = ctypes.c_void_p
C_ULONG = ctypes.c_uint
C_DWORD = ctypes.c_uint
C_BOOL = ctypes.c_uint
C_STATUS = C_ULONG
C_HANDLE = C_PVOID
C_INT_ENUM = ctypes.c_ulong  # not part of original headers


class C_DeviceListInfoNode(ctypes.Structure):
    _fields_ = [
        ("Flags", C_ULONG),
        ("Type", C_ULONG),
        ("ID", C_ULONG),
        ("LocId", C_DWORD),
        ("SerialNumber", ctypes.c_char * 16),
        ("Description", ctypes.c_char * 64),
        ("ftHandle", C_HANDLE),
    ]


class C_VersionStruct(ctypes.Structure):
    _fields_ = [
        ("chipVersion", C_DWORD),
        ("dllVersion", C_DWORD),
    ]


OPEN_BY_SERIAL_NUMBER = 1
OPEN_BY_DESCRIPTION = 2
OPEN_BY_LOCATION = 4


class Status(enum.IntEnum):
    OK = 0
    INVALID_HANDLE = enum.auto()
    DEVICE_NOT_FOUND = enum.auto()
    DEVICE_NOT_OPENED = enum.auto()
    IO_ERROR = enum.auto()
    INSUFFICIENT_RESOURCES = enum.auto()
    INVALID_PARAMETER = enum.auto()
    INVALID_BAUD_RATE = enum.auto()
    DEVICE_NOT_OPENED_FOR_ERASE = enum.auto()
    DEVICE_NOT_OPENED_FOR_WRITE = enum.auto()
    FAILED_TO_WRITE_DEVICE = enum.auto()
    EEPROM_READ_FAILED = enum.auto()
    EEPROM_WRITE_FAILED = enum.auto()
    EEPROM_ERASE_FAILED = enum.auto()
    EEPROM_NOT_PRESENT = enum.auto()
    EEPROM_NOT_PROGRAMMED = enum.auto()
    INVALID_ARGS = enum.auto()
    NOT_SUPPORTED = enum.auto()
    OTHER_ERROR = enum.auto()
    DEVICE_LIST_NOT_READY = enum.auto()

    DEVICE_NOT_SUPPORTED = 1000
    CLK_NOT_SUPPORTED = enum.auto()
    VENDER_CMD_NOT_SUPPORTED = enum.auto()
    IS_NOT_SPI_MODE = enum.auto()
    IS_NOT_I2C_MODE = enum.auto()
    IS_NOT_SPI_SINGLE_MODE = enum.auto()
    IS_NOT_SPI_MULTI_MODE = enum.auto()
    WRONG_I2C_ADDR = enum.auto()
    INVAILD_FUNCTION = enum.auto()
    INVALID_POINTER = enum.auto()
    EXCEEDED_MAX_TRANSFER_SIZE = enum.auto()
    FAILED_TO_READ_DEVICE = enum.auto()
    I2C_NOT_SUPPORTED_IN_THIS_MODE = enum.auto()
    GPIO_NOT_SUPPORTED_IN_THIS_MODE = enum.auto()
    GPIO_EXCEEDED_MAX_PORTNUM = enum.auto()
    GPIO_WRITE_NOT_SUPPORTED = enum.auto()
    GPIO_PULLUP_INVALID_IN_INPUTMODE = enum.auto()
    GPIO_PULLDOWN_INVALID_IN_INPUTMODE = enum.auto()
    GPIO_OPENDRAIN_INVALID_IN_OUTPUTMODE = enum.auto()
    INTERRUPT_NOT_SUPPORTED = enum.auto()
    GPIO_INPUT_NOT_SUPPORTED = enum.auto()
    EVENT_NOT_SUPPORTED = enum.auto()
    FUN_NOT_SUPPORT = enum.auto()


class ClockRate(enum.IntEnum):
    SYS_CLK_60 = 0
    SYS_CLK_24 = enum.auto()
    SYS_CLK_48 = enum.auto()
    SYS_CLK_80 = enum.auto()


class SPIClock(enum.IntEnum):
    CLK_NONE = 0
    CLK_DIV_2 = enum.auto()
    CLK_DIV_4 = enum.auto()
    CLK_DIV_8 = enum.auto()
    CLK_DIV_16 = enum.auto()
    CLK_DIV_32 = enum.auto()
    CLK_DIV_64 = enum.auto()
    CLK_DIV_128 = enum.auto()
    CLK_DIV_256 = enum.auto()
    CLK_DIV_512 = enum.auto()


class SPIMode(enum.IntEnum):
    SPI_IO_NONE = 0
    SPI_IO_SINGLE = 1
    SPI_IO_DUAL = 2
    SPI_IO_QUAD = 4


class SPICPOL(enum.IntEnum):
    CLK_IDLE_LOW = 0
    CLK_IDLE_HIGH = 1


class SPICPHA(enum.IntEnum):
    CLK_LEADING = 0
    CLK_TRAILING = 1


class DrivingStrength(enum.IntEnum):
    DS_4MA = 0
    DS_8MA = enum.auto()
    DS_12MA = enum.auto()
    DS_16MA = enum.auto()


FUN_ARGTYPES = {
    "FT_CreateDeviceInfoList": [POINTER(C_DWORD)],
    "FT_GetDeviceInfoList": [POINTER(C_DeviceListInfoNode), POINTER(C_DWORD)],
    "FT4222_GetVersion": [C_HANDLE, POINTER(C_VersionStruct)],
    "FT_OpenEx": [C_PVOID, C_DWORD, POINTER(C_HANDLE)],
    "FT_Close": [C_HANDLE],
    "FT4222_SetClock": [C_HANDLE, C_INT_ENUM],
    "FT4222_GetClock": [C_HANDLE, POINTER(C_INT_ENUM)],
    "FT_SetTimeouts": [C_HANDLE, C_ULONG, C_ULONG],
    "FT4222_SetSuspendOut": [C_HANDLE, C_BOOL],
    "FT4222_SetWakeUpInterrupt": [C_HANDLE, C_BOOL],
    "FT4222_UnInitialize": [C_HANDLE],
    "FT4222_SPI_SetDrivingStrength": [C_HANDLE, C_INT_ENUM, C_INT_ENUM, C_INT_ENUM],
    "FT4222_SPIMaster_Init": [
        C_HANDLE,
        C_INT_ENUM,
        C_INT_ENUM,
        C_INT_ENUM,
        C_INT_ENUM,
        ctypes.c_uint8,
    ],
    "FT4222_SPIMaster_SingleRead": [
        C_HANDLE,
        POINTER(ctypes.c_uint8),
        ctypes.c_uint16,
        POINTER(ctypes.c_uint16),
        C_BOOL,
    ],
    "FT4222_SPIMaster_SingleWrite": [
        C_HANDLE,
        POINTER(ctypes.c_uint8),
        ctypes.c_uint16,
        POINTER(ctypes.c_uint16),
        C_BOOL,
    ],
    "FT4222_SPIMaster_SingleReadWrite": [
        C_HANDLE,
        POINTER(ctypes.c_uint8),
        POINTER(ctypes.c_uint8),
        ctypes.c_uint16,
        POINTER(ctypes.c_uint16),
        C_BOOL,
    ],
}


funs = None


def _load_dll():
    global funs

    if funs is not None:
        return

    system = platform.system().lower()
    bin_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data/libft4222")
    if system == "linux":
        machine_type = platform.machine()
        sub_dir = machine_type.lower()

        if sub_dir.startswith("arm"):
            sub_dir = sub_dir[:5]  # get 5 first letters: "armv?"
        try:
            lib_path = glob(os.path.join(bin_dir, sub_dir, "libft4222.so*"))[0]
            dll = ctypes.CDLL(lib_path)
        except (IndexError, OSError):
            raise OSError(f"Unsupported machine type: '{machine_type}'") from None

        funs = {name: getattr(dll, name) for name in FUN_ARGTYPES.keys()}
    elif system == "windows":
        try:
            ft_dll = ctypes.WinDLL(os.path.join(bin_dir, "amd64", "ftd2xx.dll"))
            ft4222_dll = ctypes.CDLL(os.path.join(bin_dir, "amd64", "LibFT4222.dll"))
        except OSError:
            ft_dll = ctypes.WinDLL(os.path.join(bin_dir, "i386", "ftd2xx.dll"))
            ft4222_dll = ctypes.CDLL(os.path.join(bin_dir, "i386", "LibFT4222.dll"))
        funs = {}
        for name in FUN_ARGTYPES.keys():
            prefix = name.split("_")[0].lower()
            dll = ft4222_dll if prefix == "ft4222" else ft_dll
            funs[name] = getattr(dll, name)
    else:
        raise RuntimeError("OS not supported")

    for name, argtypes in FUN_ARGTYPES.items():
        fun = funs[name]
        fun.restype = C_STATUS
        fun.argtypes = argtypes


def check_status(status):
    if status != Status.OK.value:
        try:
            status = Status(status)
        except ValueError:
            msg = "unknown"
            err = status
        else:
            msg = status.name
            err = status.value

        raise LibFT4222Error("Error {}: {}".format(err, msg))


def get_enum_val(x):
    return x.value if isinstance(x, enum.Enum) else x


class LibFT4222Error(Exception):
    pass


class Device:
    def __init__(self, handle=None):
        self.handle = handle
        _load_dll()

    def open_ex(self):
        _locationId = b"FT4222 A"
        self.handle = C_HANDLE()
        check_status(funs["FT_OpenEx"](_locationId, OPEN_BY_DESCRIPTION, byref(self.handle)))

    def close(self):
        check_status(funs["FT_Close"](self.handle))
        self.handle = None

    def get_version(self):
        _version = C_VersionStruct()
        check_status(funs["FT4222_GetVersion"](self.handle, byref(_version)))
        return int(_version.chipVersion), int(_version.dllVersion)

    def get_clock(self):
        _clock = C_INT_ENUM()
        check_status(funs["FT4222_GetClock"](self.handle, byref(_clock)))
        return ClockRate(int(_clock.value))

    def set_clock(self, clock):
        check_status(funs["FT4222_SetClock"](self.handle, get_enum_val(clock)))

    def set_timeouts(self, read, write):
        check_status(funs["FT_SetTimeouts"](self.handle, read, write))

    def set_suspend_out(self, enable):
        check_status(funs["FT4222_SetSuspendOut"](self.handle, enable))

    def set_wake_up_interrupt(self, enable):
        check_status(funs["FT4222_SetWakeUpInterrupt"](self.handle, enable))

    def spi_master_init(
        self,
        io_line=SPIMode.SPI_IO_SINGLE,
        clock=SPIClock.CLK_NONE,
        cpol=SPICPOL.CLK_IDLE_LOW,
        cpha=SPICPHA.CLK_LEADING,
        sso_map=1,
    ):
        status = funs["FT4222_SPIMaster_Init"](
            self.handle,
            get_enum_val(io_line),
            get_enum_val(clock),
            get_enum_val(cpol),
            get_enum_val(cpha),
            sso_map,
        )
        check_status(status)

    def spi_set_driving_strength(
        self, clock=DrivingStrength.DS_8MA, io=DrivingStrength.DS_8MA, sso=DrivingStrength.DS_8MA
    ):
        status = funs["FT4222_SPI_SetDrivingStrength"](
            self.handle,
            get_enum_val(clock),
            get_enum_val(io),
            get_enum_val(sso),
        )
        check_status(status)

    def spi_master_single_read(self, num_bytes, is_end_transaction=True):
        read_buffer = (ctypes.c_uint8 * num_bytes)()
        size_transferred = ctypes.c_uint16()
        status = funs["FT4222_SPIMaster_SingleRead"](
            self.handle,
            read_buffer,
            num_bytes,
            byref(size_transferred),
            is_end_transaction,
        )

        assert size_transferred.value == num_bytes
        check_status(status)

        return bytearray(read_buffer)

    def spi_master_single_write(self, data, is_end_transaction=True):
        num_bytes = len(data)
        write_buffer = (ctypes.c_uint8 * num_bytes)(*data)
        size_transferred = ctypes.c_uint16()
        status = funs["FT4222_SPIMaster_SingleWrite"](
            self.handle,
            write_buffer,
            num_bytes,
            byref(size_transferred),
            is_end_transaction,
        )

        assert size_transferred.value == num_bytes
        check_status(status)

    def spi_master_single_read_write(self, write_data, is_end_transaction=True):
        num_bytes = len(write_data)
        read_buffer = (ctypes.c_uint8 * num_bytes)()
        write_buffer = (ctypes.c_uint8 * num_bytes)(*write_data)
        size_transferred = ctypes.c_uint16()
        status = funs["FT4222_SPIMaster_SingleReadWrite"](
            self.handle,
            read_buffer,
            write_buffer,
            num_bytes,
            byref(size_transferred),
            is_end_transaction,
        )

        assert size_transferred.value == num_bytes
        check_status(status)

        return bytearray(read_buffer)


def print_devices():
    _load_dll()

    _num_devs = C_DWORD()
    status = funs["FT_CreateDeviceInfoList"](byref(_num_devs))
    check_status(status)

    _dev_info = (C_DeviceListInfoNode * _num_devs.value)()
    status = funs["FT_GetDeviceInfoList"](_dev_info, byref(_num_devs))
    check_status(status)

    for i, v in enumerate(_dev_info):
        print("{}:".format(i))
        print("  ", v.Type)
        print("  ", v.Description.decode() or "-")
        print("  ", v.LocId)


if __name__ == "__main__":
    print_devices()
