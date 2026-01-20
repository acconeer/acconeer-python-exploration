#######################################
# Copyright (c) Acconeer AB, 2025-2026
# All rights reserved
#######################################

"""DFU config for the XC120 board firmware"""

from ._bootloader_tool import BootloaderTool


XC120_VID = 0x0483
XC120_EXPLORATION_SERVER_WINUSB_PID = 0xA449
XC120_BOOTLOADER_PID = 0xA41D


class BootLoaderXC120(BootloaderTool):
    def __init__(self):
        super().__init__(device_vid=XC120_VID, bootloader_pid=XC120_BOOTLOADER_PID)

    def device_enter_dfu(self, device_pid, device_port):
        if device_pid == XC120_BOOTLOADER_PID:
            success = True
        elif device_pid == XC120_EXPLORATION_SERVER_WINUSB_PID:
            success = self.exploration_server_to_dfu(
                XC120_VID, XC120_EXPLORATION_SERVER_WINUSB_PID
            )
        else:
            success = False
        return success
