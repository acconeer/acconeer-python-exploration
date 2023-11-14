# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar, Union, cast

from acconeer.exptool.a121 import Client, Result
from acconeer.exptool.a121._core import utils

from ._message import GeneralMessage, Message
from ._rate_calc import _RateCalculator


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

    def start_session(self) -> None:
        self._wrapped_client.start_session()
        assert self._wrapped_client.session_config is not None
        assert self._wrapped_client.extended_metadata is not None

        if self._wrapped_client.session_config.extended:
            (first_metadata, *_) = utils.iterate_extended_structure_values(
                self._wrapped_client.extended_metadata
            )
            self._rate_stats_calc = _RateCalculator(
                self._wrapped_client.session_config.update_rate,
                first_metadata.tick_period,
            )
        else:
            metadata = utils.unextend(self._wrapped_client.extended_metadata)
            self._rate_stats_calc = _RateCalculator(
                self._wrapped_client.session_config.update_rate, metadata.tick_period
            )

    def get_next(self) -> Union[Result, list[dict[int, Result]]]:
        result = self._wrapped_client.get_next()
        assert self._rate_stats_calc is not None

        if isinstance(result, Result):
            self._rate_stats_calc.update(result)
        else:
            (first_result, *_) = utils.iterate_extended_structure_values(result)
            self._rate_stats_calc.update(first_result)

        self.callback(GeneralMessage(name="rate_stats", data=self._rate_stats_calc.stats))
        self._frame_count += 1
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))
        return result

    def stop_session(self) -> None:
        result = self._wrapped_client.stop_session()
        self._frame_count = 0
        self.callback(GeneralMessage(name="rate_stats", data=None))
        self.callback(GeneralMessage(name="frame_count", data=None))
        return result
