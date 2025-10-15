# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from acconeer.exptool.flash._bootloader_tool import (
    XC120_BOOTLOADER_PID,
    XC120_EXPLORATION_SERVER_WINUSB_PID,
    BootLoaderXC120,
)
from acconeer.exptool.flash._mcumgruart import ACCONEER_XB122_MODULE_PID, McuMgrUartFlasher
from acconeer.exptool.flash._stm32uart import ACCONEER_XM_CP2105_MODULE_PID, Stm32UartFlasher


PRODUCT_PID_TO_FLASH_MAP = {
    XC120_BOOTLOADER_PID: BootLoaderXC120,
    XC120_EXPLORATION_SERVER_WINUSB_PID: BootLoaderXC120,
    ACCONEER_XM_CP2105_MODULE_PID: Stm32UartFlasher,
    ACCONEER_XB122_MODULE_PID: McuMgrUartFlasher,
}

PRODUCT_NAME_TO_FLASH_MAP = {
    "XC120": BootLoaderXC120,
    "XE125": Stm32UartFlasher,
    "XM125": Stm32UartFlasher,
    "XB122": McuMgrUartFlasher,
    "XM126": McuMgrUartFlasher,
}

EVK_TO_PRODUCT_MAP = {
    "XC120": "XC120",
    "XE125": "XM125",
    "XM125": "XM125",
    "XB122": "XM126",
    "XM126": "XM126",
}

EVKS_THAT_HAVE_FW_ON_DEVSITE = ["XC120", "XM125", "XM126"]
