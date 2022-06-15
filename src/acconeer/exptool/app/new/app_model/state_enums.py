from enum import Enum, auto


class ConnectionState(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    DISCONNECTING = auto()


class ConnectionInterface(Enum):
    SERIAL = auto()
    SOCKET = auto()


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
