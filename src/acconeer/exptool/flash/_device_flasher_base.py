# Copyright (c) Acconeer AB, 2022-2023
# All rights reserved

from __future__ import annotations

from abc import abstractmethod
from typing import Optional


class DeviceFlasherBase:
    @staticmethod
    @abstractmethod
    def flash(device_port, device_name, image_path, progress_callback=None):
        pass

    @staticmethod
    def get_boot_description(device_name: str) -> Optional[str]:
        return None
