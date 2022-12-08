# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.flash._stm32uart import ACCONEER_XM_CP2105_MODULE_PID, Stm32UartFlasher
from acconeer.exptool.flash._xc120 import (
    ACCONEER_XC120_BOARD_PROTOCOL_PID,
    ACCONEER_XC120_BOOTLOADER_PID,
    ACCONEER_XC120_EXPLORATION_SERVER_PID,
    ACCONEER_XC120_EXPLORATION_SERVER_WINUSB_PID,
    BootloaderTool,
)


PRODUCT_PID_TO_FLASH_MAP = {
    ACCONEER_XC120_BOARD_PROTOCOL_PID: BootloaderTool,
    ACCONEER_XC120_BOOTLOADER_PID: BootloaderTool,
    ACCONEER_XC120_EXPLORATION_SERVER_PID: BootloaderTool,
    ACCONEER_XC120_EXPLORATION_SERVER_WINUSB_PID: BootloaderTool,
    ACCONEER_XM_CP2105_MODULE_PID: Stm32UartFlasher,
}

PRODUCT_NAME_TO_FLASH_MAP = {
    "XC120": BootloaderTool,
    "XE125": Stm32UartFlasher,
    "XM125": Stm32UartFlasher,
}

EVK_TO_PRODUCT_MAP = {
    "XC120": "XC120",
    "XE125": "XM125",
    "XM125": "XM125",
}
