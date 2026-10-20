#######################################
# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
#######################################

"""DFU config for the XE212 board firmware"""

from ._bootloader_tool import BootloaderTool


XE212_VID = 0x0483
XE212_EXPLORATION_SERVER_WINUSB_PID = 0xA561
XE212_BOOTLOADER_PID = 0xA560
XE212_SDK_APP_PID = 0xA562
XE212_SDK_APP_PROTOCOL_SERVER_ID = 0x12


class BootLoaderXE212(BootloaderTool):
    def __init__(self):
        super().__init__(device_vid=XE212_VID, bootloader_pid=XE212_BOOTLOADER_PID)

    def device_enter_dfu(self, device_pid, device_port):
        if device_pid == XE212_BOOTLOADER_PID:
            success = True
        elif device_pid == XE212_EXPLORATION_SERVER_WINUSB_PID:
            success = self.exploration_server_to_dfu(
                XE212_VID, XE212_EXPLORATION_SERVER_WINUSB_PID
            )
        elif device_pid == XE212_SDK_APP_PID:
            success = self.protocol_server_to_dfu(device_port, XE212_SDK_APP_PROTOCOL_SERVER_ID)
        else:
            success = False
        return success
