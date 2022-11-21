import ctypes
import re
from ctypes import (
    byref,
    c_byte,
    c_ubyte,
    c_ulong,
    c_void_p,
    create_string_buffer,
    resize,
    sizeof,
    wstring_at,
)
from ctypes.wintypes import DWORD

from .winusb import WinUSBApi
from .winusbclasses import (
    DIGCF_DEVICE_INTERFACE,
    DIGCF_PRESENT,
    FILE_ATTRIBUTE_NORMAL,
    FILE_FLAG_OVERLAPPED,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GENERIC_WRITE,
    GUID,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    PipeInfo,
    SpDeviceInterfaceData,
    SpDeviceInterfaceDetailData,
    SpDevinfoData,
    UsbInterfaceDescriptor,
)
from .winusbutils import (
    Close_Handle,
    CreateFile,
    GetLastError,
    SetupDiEnumDeviceInterfaces,
    SetupDiGetClassDevs,
    SetupDiGetDeviceInterfaceDetail,
    WinUsb_ControlTransfer,
    WinUsb_FlushPipe,
    WinUsb_Free,
    WinUsb_GetAssociatedInterface,
    WinUsb_Initialize,
    WinUsb_QueryInterfaceSettings,
    WinUsb_QueryPipe,
    WinUsb_ReadPipe,
    WinUsb_SetPipePolicy,
    WinUsb_WritePipe,
)


class WinUsbPy(object):
    def __init__(self):
        self.api = WinUSBApi()
        byte_array = c_byte * 8
        self.usb_winusb_guid = GUID(
            0xDEE824EF, 0x729B, 0x4A0E, byte_array(0x9C, 0x14, 0xB7, 0x11, 0x7D, 0x33, 0xA8, 0x17)
        )
        self.handle_file = INVALID_HANDLE_VALUE
        self.handle_winusb = [c_void_p()]
        self._index = -1

    def find_all_devices(self):
        device_path_list = []
        self.handle = self.api.exec_function_setupapi(
            SetupDiGetClassDevs,
            byref(self.usb_winusb_guid),
            None,
            None,
            DWORD(DIGCF_PRESENT | DIGCF_DEVICE_INTERFACE),
        )
        sp_device_interface_data = SpDeviceInterfaceData()
        sp_device_interface_data.cb_size = sizeof(sp_device_interface_data)
        sp_device_interface_detail_data = SpDeviceInterfaceDetailData()
        sp_device_info_data = SpDevinfoData()
        sp_device_info_data.cb_size = sizeof(sp_device_info_data)

        i = 0
        required_size = DWORD(0)
        member_index = DWORD(i)
        cb_sizes = (8, 6, 5)  # different on 64 bit / 32 bit etc

        while self.api.exec_function_setupapi(
            SetupDiEnumDeviceInterfaces,
            self.handle,
            None,
            byref(self.usb_winusb_guid),
            member_index,
            byref(sp_device_interface_data),
        ):
            self.api.exec_function_setupapi(
                SetupDiGetDeviceInterfaceDetail,
                self.handle,
                byref(sp_device_interface_data),
                None,
                0,
                byref(required_size),
                None,
            )
            resize(sp_device_interface_detail_data, required_size.value)

            path = None
            for cb_size in cb_sizes:
                sp_device_interface_detail_data.cb_size = cb_size
                ret = self.api.exec_function_setupapi(
                    SetupDiGetDeviceInterfaceDetail,
                    self.handle,
                    byref(sp_device_interface_data),
                    byref(sp_device_interface_detail_data),
                    required_size,
                    byref(required_size),
                    byref(sp_device_info_data),
                )
                if ret:
                    cb_sizes = (cb_size,)
                    path = wstring_at(byref(sp_device_interface_detail_data, sizeof(DWORD)))
                    break
            if path is None:
                raise ctypes.WinError()

            pattern = r"(.*)#vid_(?P<vid>\w+)&pid_(?P<pid>\w+)(&mi_.*)?#(?P<serial>.*)#(.*)"
            match = re.fullmatch(pattern, path)
            groups = match.groupdict()
            vid = int(f"0x{groups['vid']}", 16)
            pid = int(f"0x{groups['pid']}", 16)
            serial_number = groups["serial"]
            if "&" in serial_number:
                serial_number = None

            device_path_list.append(
                {
                    "vid": vid,
                    "pid": pid,
                    "serial": serial_number,
                    "path": path,
                }
            )

            i += 1
            member_index = DWORD(i)
            required_size = DWORD(0)
            resize(sp_device_interface_detail_data, sizeof(SpDeviceInterfaceDetailData))

        return device_path_list

    def init_winusb_device(self, path):
        if path is None:
            return False

        self.handle_file = self.api.exec_function_kernel32(
            CreateFile,
            path,
            GENERIC_WRITE | GENERIC_READ,
            FILE_SHARE_WRITE | FILE_SHARE_READ,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            None,
        )

        if self.handle_file == INVALID_HANDLE_VALUE:
            return False
        result = self.api.exec_function_winusb(
            WinUsb_Initialize, self.handle_file, byref(self.handle_winusb[0])
        )
        if result == 0:
            # err = self.get_last_error_code()
            raise ctypes.WinError()
            # return False
        else:
            self._index = 0
            return True

    def close_winusb_device(self):
        result_file = 1
        if self.handle_file:
            result_file = self.api.exec_function_kernel32(Close_Handle, self.handle_file)
            if result_file:
                self.handle_file = None

        result_winusb = [self.api.exec_function_winusb(WinUsb_Free, h) for h in self.handle_winusb]
        if 0 in result_winusb:
            raise RuntimeError("Unable to close winusb handle")
        self.handle_winusb = []
        return result_file != 0

    def get_last_error_code(self):
        return self.api.exec_function_kernel32(GetLastError)

    def query_interface_settings(self, index):
        if self._index != -1:
            temp_handle_winusb = self.handle_winusb[self._index]
            interface_descriptor = UsbInterfaceDescriptor()
            result = self.api.exec_function_winusb(
                WinUsb_QueryInterfaceSettings,
                temp_handle_winusb,
                c_ubyte(0),
                byref(interface_descriptor),
            )
            if result != 0:
                return interface_descriptor
            else:
                return None
        else:
            return None

    def change_interface(self, index, alternate=0):
        new_handle = c_void_p()
        result = self.api.exec_function_winusb(
            WinUsb_GetAssociatedInterface,
            self.handle_winusb[self._index],
            c_ubyte(alternate),
            byref(new_handle),
        )
        if result != 0:
            self._index = index + 1
            self.handle_winusb.append(new_handle)
            return True
        else:
            return False

    def query_pipe(self, pipe_index):
        pipe_info = PipeInfo()
        result = self.api.exec_function_winusb(
            WinUsb_QueryPipe,
            self.handle_winusb[self._index],
            c_ubyte(0),
            pipe_index,
            byref(pipe_info),
        )
        if result != 0:
            return pipe_info
        else:
            return None

    def control_transfer(self, setup_packet, buff=None):
        if buff is not None:
            if setup_packet.length > 0:  # Host 2 Device
                buff = (c_ubyte * setup_packet.length)(*buff)
                buffer_length = setup_packet.length
            else:  # Device 2 Host
                buff = (c_ubyte * setup_packet.length)()
                buffer_length = setup_packet.length
        else:
            buff = c_ubyte()
            buffer_length = 0

        result = self.api.exec_function_winusb(
            WinUsb_ControlTransfer,
            self.handle_winusb[0],
            setup_packet,
            byref(buff),
            c_ulong(buffer_length),
            byref(c_ulong(0)),
            None,
        )
        return {"result": result != 0, "buffer": [buff]}

    def write(self, pipe_id, write_buffer):
        write_buffer = create_string_buffer(write_buffer)
        written = c_ulong(0)
        self.api.exec_function_winusb(
            WinUsb_WritePipe,
            self.handle_winusb[self._index],
            c_ubyte(pipe_id),
            write_buffer,
            c_ulong(len(write_buffer) - 1),
            byref(written),
            None,
        )
        return written.value

    def read(self, pipe_id, length_buffer):
        read_buffer = create_string_buffer(length_buffer)
        read = c_ulong(0)
        result = self.api.exec_function_winusb(
            WinUsb_ReadPipe,
            self.handle_winusb[self._index],
            c_ubyte(pipe_id),
            read_buffer,
            c_ulong(length_buffer),
            byref(read),
            None,
        )
        if result != 0:
            if read.value != length_buffer:
                return read_buffer[: read.value]
            else:
                return read_buffer
        else:
            return None

    def set_timeout(self, pipe_id, timeout):
        class POLICY_TYPE:
            SHORT_PACKET_TERMINATE = 1
            AUTO_CLEAR_STALL = 2
            PIPE_TRANSFER_TIMEOUT = 3
            IGNORE_SHORT_PACKETS = 4
            ALLOW_PARTIAL_READS = 5
            AUTO_FLUSH = 6
            RAW_IO = 7

        policy_type = c_ulong(POLICY_TYPE.PIPE_TRANSFER_TIMEOUT)
        value_length = c_ulong(4)
        value = c_ulong(int(timeout * 1000))  # in ms
        result = self.api.exec_function_winusb(
            WinUsb_SetPipePolicy,
            self.handle_winusb[self._index],
            c_ubyte(pipe_id),
            policy_type,
            value_length,
            byref(value),
        )
        return result

    def flush(self, pipe_id):
        result = self.api.exec_function_winusb(
            WinUsb_FlushPipe, self.handle_winusb[self._index], c_ubyte(pipe_id)
        )
        return result
