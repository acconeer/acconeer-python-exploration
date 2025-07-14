# Copyright (c) Acconeer AB, 2023-2025
# All rights reserved

from __future__ import annotations

from typing import Any, Callable, Generic, Optional, TypeVar, Union, cast

import typing_extensions as te

from acconeer.exptool import a121
from acconeer.exptool._core.communication import Client
from acconeer.exptool.a121._core import utils

from ._message import GeneralMessage, Message, StatusMessage
from ._rate_calc import _RateCalculator, _RateStats


ClientT = TypeVar("ClientT", bound=Client[Any, Any, Any, Any, Any])
ResultT = TypeVar("ResultT")


def _format_warning(s: str) -> str:
    return f'<b style="color: #FD5200;">Warning: {s}</b>'


_CALIBRATION_NEEDED_MESSAGE = _format_warning("Calibration needed - restart")
_DATA_SATURATED_MESSAGE = _format_warning("Data saturated - reduce gain")
_FRAME_DELAYED_MESSAGE = _format_warning("Frame delayed")


class _Extractor(te.Protocol):
    @staticmethod
    def create_rate_calculator(client: Any) -> _RateCalculator: ...

    @staticmethod
    def update_rate_calculator(calculator: _RateCalculator, result: Any) -> _RateStats: ...

    @staticmethod
    def get_status_messages(result: Any) -> list[str]: ...


class _A121Extractor(_Extractor):
    @staticmethod
    def create_rate_calculator(client: a121.Client) -> _RateCalculator:
        assert client.extended_metadata is not None
        assert client.server_info is not None

        (first_metadata, *_) = utils.iterate_extended_structure_values(client.extended_metadata)
        return _RateCalculator(client.server_info.ticks_per_second, first_metadata.tick_period)

    @staticmethod
    def update_rate_calculator(
        calculator: _RateCalculator, result: Union[a121.Result, list[dict[int, a121.Result]]]
    ) -> _RateStats:
        if isinstance(result, a121.Result):
            return calculator.update(result.tick, result.frame_delayed)
        else:
            (first_result, *_) = utils.iterate_extended_structure_values(result)
            return calculator.update(first_result.tick, first_result.frame_delayed)

    @staticmethod
    def get_status_messages(
        result: Union[a121.Result, list[dict[int, a121.Result]]],
    ) -> list[str]:
        if isinstance(result, a121.Result):
            result_list = [result]
        elif isinstance(result, list):
            result_list = list(utils.iterate_extended_structure_values(result))
        else:
            msg = f"Unexpected type for 'result': {type(result)}"
            raise AssertionError(msg)

        msgs = []
        if any(r.data_saturated for r in result_list):
            msgs.append(_DATA_SATURATED_MESSAGE)

        if any(r.calibration_needed for r in result_list):
            msgs.append(_CALIBRATION_NEEDED_MESSAGE)

        if any(r.frame_delayed for r in result_list):
            msgs.append(_FRAME_DELAYED_MESSAGE)

        return msgs


class ApplicationClient(Generic[ClientT]):
    callback: Callable[[Message], None]
    extractor_strategy: type[_Extractor]
    _wrapped_client: Client[Any, Any, Any, Any, Any]
    _rate_stats_calc: Optional[_RateCalculator]
    _frame_count: int

    def __init__(
        self,
        wrapped_client: ClientT,
        callback: Callable[[Message], None],
        extractor_strategy: type[_Extractor],
    ) -> None:
        self._wrapped_client = wrapped_client
        self.callback = callback
        self.extractor_strategy = extractor_strategy
        self._rate_stats_calc = None
        self._frame_count = 0

    def __getattr__(self, name: str) -> Any:
        """
        This is the key to the "fall-through-wrapping".
        """
        return getattr(self._wrapped_client, name)

    @classmethod
    def wrap_a121(cls, wrapped_client: ClientT, callback: Callable[[Message], None]) -> ClientT:
        """
        Factory that makes the ApplicationClient transparent from a
        typing perspective.

        The cast is necessary as we are dealing with magic here, but should hold
        up so long any overriden functions have the same type as the overriders.
        """
        return cast(ClientT, cls(wrapped_client, callback, _A121Extractor))

    def start_session(self) -> None:
        self._wrapped_client.start_session()
        self._rate_stats_calc = self.extractor_strategy.create_rate_calculator(
            self._wrapped_client
        )

    def get_next(self) -> Any:
        assert self._rate_stats_calc is not None

        result = self._wrapped_client.get_next()
        stats = self.extractor_strategy.update_rate_calculator(self._rate_stats_calc, result)

        self.callback(GeneralMessage(name="rate_stats", data=stats))
        self._frame_count += 1
        self.callback(GeneralMessage(name="frame_count", data=self._frame_count))

        for msg in self.extractor_strategy.get_status_messages(result):
            self.callback(StatusMessage(status=msg))

        return result

    def stop_session(self) -> None:
        result = self._wrapped_client.stop_session()
        self._frame_count = 0
        self.callback(GeneralMessage(name="rate_stats", data=None))
        self.callback(GeneralMessage(name="frame_count", data=None))
        return result
