# Copyright (c) Acconeer AB, 2022
# All rights reserved

import attrs


@attrs.frozen(kw_only=True)
class ServerLogMessage:
    level: str
    timestamp: int
    module: str
    log: str
