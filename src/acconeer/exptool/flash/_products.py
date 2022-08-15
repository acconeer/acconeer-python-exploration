# Copyright (c) Acconeer AB, 2022
# All rights reserved

from acconeer.exptool.flash._xc120 import (
    ACCONEER_XC120_BOARD_PROTOCOL_PID,
    ACCONEER_XC120_BOOTLOADER_PID,
    ACCONEER_XC120_EXPLORATION_SERVER_PID,
    BootloaderTool,
)


PRODUCT_FLASH_MAP = {
    ACCONEER_XC120_BOARD_PROTOCOL_PID: BootloaderTool,
    ACCONEER_XC120_BOOTLOADER_PID: BootloaderTool,
    ACCONEER_XC120_EXPLORATION_SERVER_PID: BootloaderTool,
}
