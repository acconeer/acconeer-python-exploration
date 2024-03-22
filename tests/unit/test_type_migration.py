# Copyright (c) Acconeer AB, 2024
# All rights reserved

from __future__ import annotations

import json
import typing as t

import attrs
import pytest
import typing_extensions as te

from acconeer.exptool import type_migration as tm


@attrs.frozen
class Str:
    x: str

    def to_int(self) -> Int:
        return Int(y=int(self.x))

    @classmethod
    def from_json(cls, json_str: str) -> Str:
        return cls(**json.loads(json_str))


@attrs.frozen
class Int:
    y: int

    def to_float(self) -> Float:
        return Float(z=float(self.y))

    @classmethod
    def from_json(cls, json_str: str) -> Int:
        return cls(**json.loads(json_str))


@attrs.frozen
class Float:
    z: float

    @classmethod
    def from_json(cls, json_str: str) -> Float:
        return cls(**json.loads(json_str))

    @classmethod
    def from_float(cls, number: float) -> Float:
        return Float(z=number)

    def to_float2(self, extra: tm.Completer[float]) -> Float2:
        return Float2(self, b=extra(float))


@attrs.frozen
class Float2:
    a: Float
    b: float


_SG: te.TypeAlias = tm.Epoch[Float, te.Never, t.Union[str, Str, Int, float]]
_NC: te.TypeAlias = tm.Epoch[Float2, float, t.Union[str, Str, Int, Float, float]]


@pytest.fixture
def simple_graph() -> _SG:
    graph = (
        tm.start(Str)
        .load(str, Str.from_json, fail=[TypeError, json.JSONDecodeError])
        .nop()
        .epoch(Int, Str.to_int, fail=[])
        .load(str, Int.from_json, fail=[TypeError, json.JSONDecodeError])
        .nop()
        .epoch(Float, Int.to_float, fail=[])
        .load(float, Float.from_float, fail=[])
        .load(str, Float.from_json, fail=[TypeError, json.JSONDecodeError])
    )
    return graph


@pytest.mark.parametrize(
    "inp",
    ['{"x": "10"}', '{"y": 10}', '{"z": 10.0}', Str(x="10"), Int(y=10), 10.0],
    ids=repr,
)
def test_migrate_properly_migrates_all_leaves(simple_graph: _SG, inp: t.Any) -> None:
    assert simple_graph.migrate(inp) == Float(z=10.0)


def test_api_missuse_raises_type_errors(simple_graph: _SG) -> None:
    with pytest.raises(TypeError):
        # first pos should be an instance of "type"
        simple_graph.epoch(1, lambda x: x)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        # second pos should be a callable
        simple_graph.epoch(int, 1)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        # first pos should be an instance of "type"
        simple_graph.load(1, lambda x: x)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        # second pos should be a callable
        simple_graph.load(int, 1)  # type: ignore[arg-type]


@pytest.mark.parametrize("inp", ['{"a": 10}', "invalid_json"], ids=repr)
def test_migrate_fails_on_not_applicable_input(simple_graph: _SG, inp: str) -> None:
    with pytest.raises(tm.MigrationError):
        simple_graph.migrate(inp)


def test_migrate_raises_type_error_if_input_is_of_wrong_type(simple_graph: _SG) -> None:
    with pytest.raises(TypeError):
        simple_graph.migrate(None)  # type: ignore[call-overload]


@pytest.mark.parametrize("inp", ['{"a": 10}', "invalid_json"], ids=repr)
def test_migrate_exhausted_error_message_contain_input(simple_graph: _SG, inp: str) -> None:
    with pytest.raises(tm.MigrationError, match=inp):
        simple_graph.migrate(inp)


@pytest.fixture
def needs_extra_context(simple_graph: _SG) -> _NC:
    nc = simple_graph.contextual_epoch(Float2, Float.to_float2, fail=[])
    return nc


def test_raises_error_if_no_completer_is_provided(needs_extra_context: _NC) -> None:
    with pytest.raises(RuntimeError, match=f"No completion for {float!s}"):
        needs_extra_context.migrate('{"x": 10}')  # type: ignore[call-arg]


def test_can_migrate_if_completer_is_provided(needs_extra_context: _NC) -> None:
    def completer(t: type[float]) -> float:
        assert issubclass(t, float)
        return 42.0

    migrated = needs_extra_context.migrate('{"x": "10"}', completer)
    assert migrated == Float2(a=Float(10.0), b=42.0)


@pytest.mark.parametrize("exception_type", [ValueError, TypeError, RuntimeError])
def test_migrate_fails_with_completer_error_if_completer_raises(
    needs_extra_context: _NC, exception_type: type[Exception]
) -> None:
    def completer(_: t.Any) -> float:
        msg = "In completer!"
        raise exception_type(msg)

    with pytest.raises(exception_type, match="In completer!"):
        _ = needs_extra_context.migrate('{"x": "10"}', completer)
