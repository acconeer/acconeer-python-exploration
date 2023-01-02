# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar, Union, cast

from acconeer.exptool.a121 import Client, Result, _RateCalculator
from acconeer.exptool.a121._core import utils
from acconeer.exptool.a121._core.mediators import Recorder

from ._message import GeneralMessage, Message


ClientT = TypeVar("ClientT", bound=Client)


class ApplicationClient:

    callback: Callable[[Message], None]
    _wrapped_client: Client
    _rate_stats_calc: Optional[_RateCalculator]
    _frame_count: int

    def __init__(self, wrapped_client: Client, callback: Callable[[Message], None]) -> None:
        self._wrapped_client = wrapped_client
        self.callback = callback
        self._rate_stats_calc = None
        self._frame_count = 0

    def __getattr__(self, name: str) -> Any:
        """
        This is the key to the "fall-through-wrapping".
        """
        return getattr(self._wrapped_client, name)

    @classmethod
    def wrap(cls, wrapped_client: ClientT, callback: Callable[[Message], None]) -> ClientT:
        """
        Factory that makes the ApplicationClient transparent from a
        typing perspective.

        The cast is necessary as we are dealing with magic here, but should hold
        up so long any overriden functions have the same type as the overriders.
        """
        return cast(ClientT, cls(wrapped_client, callback))

    def start_session(self, recorder: Optional[Recorder] = None) -> None:
        self._wrapped_client.start_session(recorder)
        assert self._wrapped_client.session_config is not None
        assert self._wrapped_client.extended_metadata is not None

        if self._wrapped_client.session_config.extended:
            self._rate_stats_calc = _RateCalculator(
                self._wrapped_client.session_config, self._wrapped_client.extended_metadata
            )
        else:
            metadata = utils.unextend(self._wrapped_client.extended_metadata)
            self._rate_stats_calc = _RateCalculator(self._wrapped_client.session_config, metadata)

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        results = self._wrapped_client.get_next()
        assert self._rate_stats_calc is not None
        self._rate_stats_calc.update(results)
        self.callback(GeneralMessage(name="rate_stats", data=self._rate_stats_calc.stats))
        self._frame_count += 1
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))
        return results

    def stop_session(self) -> Any:
        result = self._wrapped_client.stop_session()
        self._frame_count = 0
        self.callback(GeneralMessage(name="rate_stats", data=None))
        self.callback(GeneralMessage(name="frame_count", data=None))
        return result
