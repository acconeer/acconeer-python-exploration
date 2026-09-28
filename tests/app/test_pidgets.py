# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import enum
import typing as t

import pytest

from PySide6.QtWidgets import QWidget

from acconeer.exptool.app.new.ui.components import pidgets


def _class_is_ABC(c: type) -> bool:
    return bool(getattr(c, "__abstractmethods__", False))


def _all_subclasses(root: type) -> list[type]:
    """
    Finds (recurively) all subclasses of the superclass 'root'.
    (T.y. unutbu@SO, https://stackoverflow.com/a/3862957)
    """
    direct_subclasses = list(root.__subclasses__())
    return direct_subclasses + [
        indirect_subclass
        for direct_subclass in direct_subclasses
        for indirect_subclass in _all_subclasses(direct_subclass)
    ]


def _mock_hook(*args: t.Any, **kwargs: t.Any) -> None:
    pass


class TestPidgets:
    @pytest.fixture(
        params=[
            pytest.param((_mock_hook,), id="Hooks in a tuple"),
            pytest.param([_mock_hook], id="Hooks in a list"),
            pytest.param(_mock_hook, id="Single hook (not in collection)"),
        ]
    )
    def hooks_argument(self, request: pytest.FixtureRequest) -> t.Any:
        return request.param

    @pytest.mark.parametrize("factory_class", _all_subclasses(pidgets.PidgetFactory))
    def test_pidget_factory(
        self, factory_class: type[pidgets.PidgetFactory], hooks_argument: t.Any
    ) -> None:
        EXTRA_KWARGS: dict[type, dict[str, t.Any]] = {
            pidgets.EnumPidgetFactory: dict(enum_type=enum.Enum, label_mapping={}),
            pidgets.OptionalEnumPidgetFactory: dict(enum_type=enum.Enum, label_mapping={}),
            pidgets.ComboboxPidgetFactory: dict(items=[]),
            pidgets.SensorIdPidgetFactory: dict(items=[]),
            pidgets.FloatSliderPidgetFactory: dict(limits=(None, None)),
            pidgets.FloatRangeSliderPidgetFactory: dict(limits=(None, None)),
            pidgets.OptionalFloatRangeSliderPidgetFactory: dict(limits=(None, None)),
            pidgets.IntFlagPidgetFactory: dict(num_bits=1),
        }
        if _class_is_ABC(factory_class):
            pytest.xfail(f"{factory_class.__name__} is abstract.")

        factory = factory_class(
            name_label_text="",
            name_label_tooltip="tt",
            hooks=hooks_argument,
            **EXTRA_KWARGS.get(factory_class, {}),
        )

        # the hooks attribute needs to be iterable
        assert isinstance(factory.hooks, t.Iterable)

    @pytest.mark.parametrize("group_class", _all_subclasses(pidgets.PidgetGroup))
    def test_create_pidget_group(
        self, group_class: type[pidgets.PidgetGroup], hooks_argument: t.Any
    ) -> None:
        EXTRA_KWARGS: dict[type, dict[str, t.Any]] = {
            pidgets.CollapsiblePidgetGroup: dict(label=":)", collapsed=True)
        }
        group = group_class(
            hooks=hooks_argument,
            **EXTRA_KWARGS.get(group_class, {}),
        )

        # the hooks attribute needs to be iterable
        assert isinstance(group.hooks, t.Iterable)

        # the group also needs to be hashable (designed to be used as keys in a dict)
        hash(group)


@pytest.mark.usefixtures("qapplication")
class TestOptionalFloatRangeSliderPidget:
    @pytest.fixture
    def pidget(self) -> t.Iterator[pidgets.OptionalFloatRangeSliderPidget]:
        parent = QWidget()
        factory = pidgets.OptionalFloatRangeSliderPidgetFactory(
            name_label_text="Bounds:",
            name_label_tooltip="Bounds.",
            limits=(-10.0, 10.0),
            init_set_value=(-2.0, 0.5),
            decimals=2,
        )
        yield factory.create(parent)

    def test_checking_starts_from_the_unset_value(
        self, pidget: pidgets.OptionalFloatRangeSliderPidget
    ) -> None:
        pidget.set_data(None)
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        pidget.set_unset_value((-1.0, 1.5))

        assert updates == []
        assert pidget.get_data() is None

        pidget._none_checkbox.setChecked(True)

        assert updates == [(-1.0, 1.5)]

    def test_unset_value_is_ignored_while_set(
        self, pidget: pidgets.OptionalFloatRangeSliderPidget
    ) -> None:
        pidget.set_data((-1.0, 1.0))

        pidget.set_unset_value((-2.0, 0.5))

        assert pidget.get_data() == (-1.0, 1.0)
