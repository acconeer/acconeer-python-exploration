# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import traceback
from typing import Callable, Dict, Optional

from ._message import LogMessage, Message


class BackendLoggerError(Exception):
    pass


class BackendLogger:
    _callback: Optional[Callable[[Message], None]] = None
    _instances: Dict[str, BackendLogger] = {}

    def __init__(self, name: str):
        self.name = name

    def _log(self, log_level: str, log_string: str) -> None:
        if not BackendLogger._callback:
            msg = "BackendLogger not initialized"
            raise BackendLoggerError(msg)
        BackendLogger._callback(
            LogMessage(module_name=self.name, log_level=log_level, log_string=log_string)
        )

    def critical(self, log_string: str) -> None:
        self._log("CRITICAL", log_string)

    def error(self, log_string: str) -> None:
        self._log("ERROR", log_string)

    def exception(self, exception: BaseException) -> None:
        tb = "\n".join(traceback.format_tb(exception.__traceback__))
        self._log(
            "ERROR",
            f"An exception was raised:\n{tb}{type(exception).__name__}: {exception}",
        )

    def warning(self, log_string: str) -> None:
        self._log("WARNING", log_string)

    def info(self, log_string: str) -> None:
        self._log("INFO", log_string)

    def debug(self, log_string: str) -> None:
        self._log("DEBUG", log_string)

    @staticmethod
    def set_callback(callback: Callable[[Message], None]) -> None:
        BackendLogger._callback = callback

    @staticmethod
    def getLogger(name: str) -> BackendLogger:
        logger = BackendLogger._instances.get(name)
        if not logger:
            logger = BackendLogger(name)
            BackendLogger._instances[name] = logger
            logger.debug(f"BackendLogger for {name} initialized")
        return logger
