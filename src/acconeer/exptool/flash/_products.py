# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from acconeer.exptool._artifact_repository import Artifact
from acconeer.exptool.flash._bootloader_tool import (
    XC120_BOOTLOADER_PID,
    XC120_EXPLORATION_SERVER_WINUSB_PID,
    XE212_BOOTLOADER_PID,
    XE212_EXPLORATION_SERVER_WINUSB_PID,
    BootLoaderXC120,
    BootLoaderXE212,
)
from acconeer.exptool.flash._mcumgruart import ACCONEER_XB122_MODULE_PID, McuMgrUartFlasher
from acconeer.exptool.flash._stm32uart import ACCONEER_XM_CP2105_MODULE_PID, Stm32UartFlasher


PRODUCT_PID_TO_FLASH_MAP = {
    XC120_BOOTLOADER_PID: BootLoaderXC120,
    XC120_EXPLORATION_SERVER_WINUSB_PID: BootLoaderXC120,
    XE212_BOOTLOADER_PID: BootLoaderXE212,
    XE212_EXPLORATION_SERVER_WINUSB_PID: BootLoaderXE212,
    ACCONEER_XM_CP2105_MODULE_PID: Stm32UartFlasher,
    ACCONEER_XB122_MODULE_PID: McuMgrUartFlasher,
}

PRODUCT_NAME_TO_FLASH_MAP = {
    "XC120": BootLoaderXC120,
    "XE212": BootLoaderXE212,
    "XE125": Stm32UartFlasher,
    "XM125": Stm32UartFlasher,
    "XB122": McuMgrUartFlasher,
    "XM126": McuMgrUartFlasher,
}

EVK_TO_PRODUCT_MAP = {
    "XC120": "XC120",
    "XE212": "XE212",
    "XE125": "XM125",
    "XM125": "XM125",
    "XB122": "XM126",
    "XM126": "XM126",
}

PRODUCT_NAME_TO_ARTIFACT = {
    "XC120": Artifact.XC120_EXPLORATION_SERVER,
    "XM125": Artifact.XM125_EXPLORATION_SERVER,
    "XM126": Artifact.XM126_EXPLORATION_SERVER,
    "XE212": Artifact.XE212_EXPLORATION_SERVER,
}
