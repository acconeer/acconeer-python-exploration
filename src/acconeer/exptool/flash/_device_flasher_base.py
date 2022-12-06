# Copyright (c) Acconeer AB, 2022
# All rights reserved

from abc import abstractmethod


class DeviceFlasherBase:
    @staticmethod
    @abstractmethod
    def flash(device_port, device_name, image_path, progress_callback=None):
        pass
