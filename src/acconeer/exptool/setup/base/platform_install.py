# Copyright (c) Acconeer AB, 2022-2026
# All rights reserved

from __future__ import annotations

import abc

from .setup_group import SetupGroup


class PlatformInstall(SetupGroup):
    """Base class and registry for platform install scripts"""

    __registry: dict[str, type[PlatformInstall]] = {}

    @classmethod
    @abc.abstractmethod
    def get_key(cls) -> str:
        """Gets the key of the platform.

        This is the same key that gets displayed in the selection menu and is
        used with the `--platform` command line argument.
        """

    @classmethod
    def from_key(cls, platform_key: str) -> PlatformInstall | None:
        """Constructs a Platform subclass that has been registered"""
        subclass = cls.__registry.get(platform_key)
        if subclass is None:
            return None
        else:
            return subclass()

    @classmethod
    def platforms(cls) -> list[str]:
        """Returns the list of keys that are registered"""
        return list(cls.__registry.keys())

    @classmethod
    def register(cls, subclass: type[PlatformInstall]) -> type[PlatformInstall]:
        """Registers a subclass"""
        if not issubclass(subclass, cls):
            msg = f"{subclass.__name__!r} needs to be a subclass of {cls.__name__}."
            raise TypeError(msg)
        cls.__registry[subclass.get_key()] = subclass
        return subclass
