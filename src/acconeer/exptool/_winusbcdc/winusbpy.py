import ctypes
import struct
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
    DIGCF_ALLCLASSES,
    DIGCF_DEFAULT,
    DIGCF_DEVICE_INTERFACE,
    DIGCF_PRESENT,
    DIGCF_PROFILE,
    ERROR_IO_INCOMPLETE,
    ERROR_IO_PENDING,
    FILE_ATTRIBUTE_NORMAL,
    FILE_FLAG_OVERLAPPED,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GENERIC_WRITE,
    GUID,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    Overlapped,
    PipeInfo,
    SpDeviceInterfaceData,
    SpDeviceInterfaceDetailData,
    SpDevinfoData,
    UsbInterfaceDescriptor,
)
from .winusbutils import (
    SPDRP_FRIENDLYNAME,
    Close_Handle,
    CreateFile,
    GetLastError,
    SetupDiEnumDeviceInterfaces,
    SetupDiGetClassDevs,
    SetupDiGetDeviceInterfaceDetail,
    SetupDiGetDeviceRegistryProperty,
    WinUsb_ControlTransfer,
    WinUsb_FlushPipe,
    WinUsb_Free,
    WinUsb_GetAssociatedInterface,
    WinUsb_GetOverlappedResult,
    WinUsb_Initialize,
    WinUsb_QueryDeviceInformation,
    WinUsb_QueryInterfaceSettings,
    WinUsb_QueryPipe,
    WinUsb_ReadPipe,
    WinUsb_SetPipePolicy,
    WinUsb_WritePipe,
    is_device,
)


def is_64bit():
    return struct.calcsize("P") * 8 == 64


class WinUsbPy(object):
    def __init__(self):
        self.api = WinUSBApi()
        byte_array = c_byte * 8
        self.usb_device_guid = GUID(
            0xA5DCBF10, 0x6530, 0x11D2, byte_array(0x90, 0x1F, 0x00, 0xC0, 0x4F, 0xB9, 0x51, 0xED)
        )
        self.usb_winusb_guid = GUID(
            0xDEE824EF, 0x729B, 0x4A0E, byte_array(0x9C, 0x14, 0xB7, 0x11, 0x7D, 0x33, 0xA8, 0x17)
        )
        self.usb_composite_guid = GUID(
            0x36FC9E60, 0xC465, 0x11CF, byte_array(0x80, 0x56, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00)
        )
        self.handle_file = INVALID_HANDLE_VALUE
        self.handle_winusb = [c_void_p()]
        self._index = -1
        self.device_paths = {}  # type: dict

    def list_usb_devices(
        self,
        default=False,
        present=False,
        allclasses=False,
        profile=False,
        deviceinterface=False,
        vid=None,
        pid=None,
        name=None,
    ):
        self.device_paths = {}
        value = 0x00000000
        try:
            if default:
                value |= DIGCF_DEFAULT
            if present:
                value |= DIGCF_PRESENT
            if allclasses:
                value |= DIGCF_ALLCLASSES
            if profile:
                value |= DIGCF_PROFILE
            if deviceinterface:
                value |= DIGCF_DEVICE_INTERFACE

        except KeyError:
            if value == 0x00000000:
                value = 0x00000010
            pass

        flags = DWORD(value)
        self.handle = self.api.exec_function_setupapi(
            SetupDiGetClassDevs, byref(self.usb_winusb_guid), None, None, flags
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

            if vid is not None and pid is not None:
                if is_device(name, vid, pid, path):
                    self.device_paths[path] = path
                    return self.device_paths
            else:

                # friendly name
                uname = path
                buff_friendly_name = ctypes.create_unicode_buffer(250)
                if self.api.exec_function_setupapi(
                    SetupDiGetDeviceRegistryProperty,
                    self.handle,
                    byref(sp_device_info_data),
                    SPDRP_FRIENDLYNAME,
                    None,
                    ctypes.byref(buff_friendly_name),
                    ctypes.sizeof(buff_friendly_name) - 1,
                    None,
                ):

                    uname = buff_friendly_name.value
                # else:
                #     err = self.get_last_error_code()
                #     # print(ctypes.WinError())
                self.device_paths[uname] = path
                if name is not None and uname == name:
                    return self.device_paths
            i += 1
            member_index = DWORD(i)
            required_size = c_ulong(0)
            resize(sp_device_interface_detail_data, sizeof(SpDeviceInterfaceDetailData))
        return self.device_paths

    def find_device(self, path):
        return is_device(self._name, self._vid, self._pid, path)

    def init_winusb_device(self, name, vid, pid):
        self._vid = vid
        self._pid = pid
        self._name = name
        path = None
        try:
            for name, p in self.device_paths.items():
                if self.find_device(name) or self.find_device(p):
                    path = p
                    break

        except IndexError:
            return False

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

    def query_device_info(self, query=1):
        info_type = c_ulong(query)
        buff = (c_void_p * 1)()
        buff_length = c_ulong(sizeof(c_void_p))
        result = self.api.exec_function_winusb(
            WinUsb_QueryDeviceInformation,
            self.handle_winusb[self._index],
            info_type,
            byref(buff_length),
            buff,
        )
        if result != 0:
            return buff[0]
        else:
            return -1

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

    def _overlapped_read_do(self, pipe_id):
        self.olread_ol.Internal = 0
        self.olread_ol.InternalHigh = 0
        self.olread_ol.Offset = 0
        self.olread_ol.OffsetHigh = 0
        self.olread_ol.Pointer = 0
        self.olread_ol.hEvent = 0
        result = self.api.exec_function_winusb(
            WinUsb_ReadPipe,
            self.handle_winusb[self._index],
            c_ubyte(pipe_id),
            self.olread_buf,
            c_ulong(self.olread_buflen),
            byref(c_ulong(0)),
            byref(self.olread_ol),
        )
        if result != 0:
            return True
        else:
            return False

    def overlapped_read_init(self, pipe_id, length_buffer):
        self.olread_ol = Overlapped()
        self.olread_buf = create_string_buffer(length_buffer)
        self.olread_buflen = length_buffer
        return self._overlapped_read_do(pipe_id)

    def overlapped_read(self, pipe_id):
        """keep on reading overlapped, return bytearray, empty if nothing to read, None if err"""
        rl = c_ulong(0)
        result = self.api.exec_function_winusb(
            WinUsb_GetOverlappedResult,
            self.handle_winusb[self._index],
            byref(self.olread_ol),
            byref(rl),
            False,
        )
        if result == 0:
            if (
                self.get_last_error_code() == ERROR_IO_PENDING
                or self.get_last_error_code() == ERROR_IO_INCOMPLETE
            ):
                return ""
            else:
                return None
        else:
            ret = str(self.olread_buf[0 : rl.value])
            self._overlapped_read_do(pipe_id)
            return ret
