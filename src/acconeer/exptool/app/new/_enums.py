# Copyright (c) Acconeer AB, 2022
# All rights reserved

from enum import Enum, auto


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()


class ConnectionInterface(Enum):
    SERIAL = auto()
    SOCKET = auto()
    USB = auto()
    SIMULATED = auto()


class PluginState(Enum):
    """Describes what state the plugin is in.

    Theese are the possible state transitions:

           +-------+      +---------------+
        +->|LOADING|-+  +>|LOADED_STARTING|-+
        |  +-------+ |  | +---------------+ |
        |            v  |                   v
    +---+----+   +------+----+      +-----------+
    |UNLOADED|   |LOADED_IDLE|      |LOADED_BUSY|
    +--------+   +----+------+      +-------+---+
        ^             | ^                   |
        | +---------+ | | +---------------+ |
        +-|UNLOADING|<+ +-|LOADED_STOPPING|<+
          +---------+     +---------------+
    """

    UNLOADED = auto()
    UNLOADING = auto()
    LOADING = auto()
    LOADED_IDLE = auto()
    LOADED_STARTING = auto()
    LOADED_BUSY = auto()
    LOADED_STOPPING = auto()

    @property
    def is_loaded(self) -> bool:
        return self in {
            self.LOADED_IDLE,
            self.LOADED_STARTING,
            self.LOADED_BUSY,
            self.LOADED_STOPPING,
        }

    @property
    def is_steady(self) -> bool:
        return self in {
            self.UNLOADED,
            self.LOADED_IDLE,
        }


class PluginFamily(Enum):
    SERVICE = "Services"
    DETECTOR = "Detectors"
    EXAMPLE_APP = "Example apps"


class PluginGeneration(Enum):
    A111 = "a111"
    A121 = "a121"
