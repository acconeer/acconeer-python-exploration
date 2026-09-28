# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations


class DeviceFlasherBase:
    def flash(self, device_port, device_name, image_path, progress_callback=None) -> None:
        pass

    @staticmethod
    def get_boot_description(device_name: str) -> str | None:
        return None

    @staticmethod
    def get_post_dfu_description(device_name: str) -> str | None:
        return None
