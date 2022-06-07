from __future__ import annotations

import abc
from typing import Any, Generic, Optional, Tuple, TypeVar

import attrs


T = TypeVar("T")


class Response(abc.ABC, Generic[T]):
    @property
    def outcomes(self) -> Tuple[Optional[Success[T]], Optional[Error[T]]]:
        """Enables an unpacking syntax for Response objects.

        usage:
            response = Response(...)
            success, error = response.outcomes

            if success:
                ...
            if error:
                ...
        """
        return self.success, self.error

    @property
    @abc.abstractmethod
    def error(self) -> Optional[Error[T]]:
        pass

    @property
    @abc.abstractmethod
    def success(self) -> Optional[Success[T]]:
        pass

    def __bool__(self) -> bool:
        return True


@attrs.frozen
class Success(Response[T]):
    source: Any
    aspect: Optional[str]
    data: T

    @property
    def error(self) -> Optional[Error[T]]:
        return None

    @property
    def success(self) -> Optional[Success[T]]:
        return self


@attrs.frozen
class Error(Response[T]):
    source: Any
    aspect: Optional[str]
    message: str

    @property
    def error(self) -> Optional[Error[T]]:
        return self

    @property
    def success(self) -> Optional[Success[T]]:
        return None
