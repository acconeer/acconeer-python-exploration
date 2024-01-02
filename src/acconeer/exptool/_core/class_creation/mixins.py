# Copyright (c) Acconeer AB, 2023-2024
# All rights reserved

from __future__ import annotations

import enum
import json
import typing as t

import attrs
import typing_extensions as te


class MyJsonEncoder(json.JSONEncoder):
    def default(self, obj: t.Any) -> t.Any:
        if isinstance(obj, enum.Enum):
            return obj.name

        elif isinstance(obj, complex):
            return {"real": obj.real, "imag": obj.imag}

        return json.JSONEncoder.default(self, obj)


def as_complex(dct: t.Any) -> t.Any:
    if "real" in dct and "imag" in dct:
        return complex(dct["real"], dct["imag"])

    return dct


class AttrsMappingTransformsMixin:
    """Mixin that provides common transform methods to an attrs class.

    The methods are:
    - to_dict
    - from_dict
    - to_json
    - from_json

    If the attrs instance is composed of other attrs instances,
    that needs to be handled by overriding ``from_dict``, where each
    of the members that are attrs instances are constructed manually.

    Example:

    >>> @attrs.mutable
    ... class Inner(AttrsMappingTransformsMixin):
    ...     foo: int
    >>>
    >>> @attrs.mutable
    ... class Outer(AttrsMappingTransformsMixin):
    ...     inner: Inner
    >>>
    >>> Outer(Inner(1)).to_dict()
    {'inner': {'foo': 1}}
    >>> decoded = Outer.from_dict(  # Not overriding from_dict will improperly decode the instance:
    ...     Outer(Inner(1)).to_dict()
    ... )
    >>> decoded
    Outer(inner={'foo': 1})
    >>> @attrs.mutable
    ... class Outer(AttrsMappingTransformsMixin):
    ...     inner: Inner
    ...
    ...     @classmethod
    ...     def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
    ...          return cls(
    ...              **{
    ...                  **dict_repr,
    ...                  "inner": Inner.from_dict(dict_repr["inner"]),
    ...              }
    ...          )
    >>> Outer.from_dict(
    ...     Outer(Inner(1)).to_dict()
    ... )
    Outer(inner=Inner(foo=1))

    Complex numbers, which JSON lacks, survive ``to_json`` and ``from_json``:

    >>> @attrs.frozen
    ... class Gain(AttrsMappingTransformsMixin):
    ...     value: complex
    >>> Gain(1 + 2j).to_json()
    '{"value": {"real": 1.0, "imag": 2.0}}'
    >>> Gain.from_json(Gain(1 + 2j).to_json())
    Gain(value=(1+2j))
    """

    def to_dict(self) -> dict[str, t.Any]:
        if not attrs.has(type(self)):
            msg = f"{type(self).__name__} is not an attrs instance."
            raise TypeError(msg)

        # type missmatch is handled by the above check
        return attrs.asdict(self)  # type: ignore[arg-type]

    @classmethod
    def from_dict(cls, dict_repr: dict[str, t.Any]) -> te.Self:
        return cls(**dict_repr)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), cls=MyJsonEncoder)

    @classmethod
    def from_json(cls, json_str: str) -> te.Self:
        return cls.from_dict(json.loads(json_str, object_hook=as_complex))
