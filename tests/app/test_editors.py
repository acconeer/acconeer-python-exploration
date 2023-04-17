# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import copy
import enum
import typing as t
from functools import partial
from unittest.mock import Mock

import attrs
import pytest

from PySide6.QtWidgets import QApplication

import acconeer.exptool.app.new.ui.plugin_components as pc
from acconeer.exptool import a121


T = t.TypeVar("T")


@attrs.frozen(kw_only=True)
class EditorFixture(t.Generic[T]):
    editor_class: t.Type[pc.DataEditor[T]]
    data_prototype: T
    good_ui_edit: t.Callable[[pc.DataEditor[T]], t.Any]
    bad_ui_edit: t.Callable[[pc.DataEditor[T]], t.Any]
    read_ui: t.Callable[[pc.DataEditor[T]], t.Any]
    noop_ui_edit: t.Callable[[pc.DataEditor[T]], t.Any]
    editor_kwargs: dict[str, t.Any] = attrs.field(factory=dict)

    @property
    def data(self) -> T:
        return copy.deepcopy(self.data_prototype)

    def get_editor(self) -> pc.DataEditor[T]:
        editor = self.editor_class(**self.editor_kwargs)
        editor.set_data(self.data)
        return editor


@attrs.frozen
class StubAttrsClass:
    a: int = attrs.field(validator=attrs.validators.gt(0))


class StubEnum(enum.Enum):
    A = enum.auto()
    B = enum.auto()


@pytest.fixture(autouse=True, scope="module")
def qapplication() -> QApplication:
    return QApplication()


@pytest.fixture(
    params=[
        EditorFixture(
            editor_class=pc.AttrsConfigEditor,
            editor_kwargs={
                "title": "title",
                "factory_mapping": {"a": pc.pidgets.IntPidgetFactory(name_label_text="")},
            },
            data_prototype=StubAttrsClass(1),
            good_ui_edit=partial(pc.AttrsConfigEditor._update_config_aspect, aspect="a", value=2),
            bad_ui_edit=partial(pc.AttrsConfigEditor._update_config_aspect, aspect="a", value=-1),
            noop_ui_edit=partial(pc.AttrsConfigEditor._update_config_aspect, aspect="a", value=1),
            read_ui=lambda ace: ace._pidget_mapping["a"].get_data(),
        ),
        EditorFixture(
            editor_class=pc.SessionConfigEditor,
            data_prototype=a121.SessionConfig(),
            good_ui_edit=partial(pc.SessionConfigEditor._update_update_rate, value=1.0),
            bad_ui_edit=partial(pc.SessionConfigEditor._update_update_rate, value=-1.0),
            noop_ui_edit=partial(
                pc.SessionConfigEditor._update_update_rate, value=a121.SessionConfig().update_rate
            ),
            read_ui=lambda sce: sce._update_rate_pidget.get_data(),
        ),
        EditorFixture(
            editor_class=pc.SensorConfigEditor,
            data_prototype=a121.SensorConfig(),
            good_ui_edit=partial(
                pc.SensorConfigEditor._update_sensor_config_aspect, aspect="frame_rate", value=1.0
            ),
            bad_ui_edit=partial(
                pc.SensorConfigEditor._update_sensor_config_aspect, aspect="frame_rate", value=-1.0
            ),
            noop_ui_edit=partial(
                pc.SensorConfigEditor._update_sensor_config_aspect,
                aspect="frame_rate",
                value=a121.SensorConfig().frame_rate,
            ),
            read_ui=lambda sce: sce._sensor_config_pidgets["frame_rate"].get_data(),
        ),
        EditorFixture(
            editor_class=pc.SubsweepConfigEditor,
            data_prototype=a121.SubsweepConfig(),
            good_ui_edit=partial(
                pc.SubsweepConfigEditor._update_subsweep_config_aspect, aspect="hwaas", value=5
            ),
            bad_ui_edit=partial(
                pc.SubsweepConfigEditor._update_subsweep_config_aspect, aspect="hwaas", value=-1
            ),
            noop_ui_edit=partial(
                pc.SubsweepConfigEditor._update_subsweep_config_aspect,
                aspect="hwaas",
                value=a121.SubsweepConfig().hwaas,
            ),
            read_ui=lambda sce: sce._subsweep_config_pidgets["hwaas"].get_data(),
        ),
    ],
    ids=lambda ef: str(ef.editor_class.__name__),
)
def config_editor_fixt(request: pytest.FixtureRequest) -> EditorFixture[t.Any]:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(
    params=[
        EditorFixture(
            editor_class=pc.pidgets.IntPidget,
            editor_kwargs={
                "factory": pc.pidgets.IntPidgetFactory(name_label_text="", limits=(0, 2)),
                "parent": None,
            },
            data_prototype=1,
            good_ui_edit=lambda ip: ip._spin_box.setValue(2),
            bad_ui_edit=lambda ip: ip._spin_box.setValue(-1),
            noop_ui_edit=lambda ip: ip._spin_box.setValue(1),
            read_ui=lambda ip: ip._spin_box.value(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.OptionalIntPidget,
            editor_kwargs={
                "factory": pc.pidgets.OptionalIntPidgetFactory(name_label_text="", limits=(0, 2)),
                "parent": None,
            },
            data_prototype=1,
            good_ui_edit=lambda oip: oip._spin_box.setValue(2),
            bad_ui_edit=lambda oip: oip._spin_box.setValue(-1),
            noop_ui_edit=lambda oip: oip._spin_box.setValue(1),
            read_ui=lambda oip: oip._spin_box.value(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.FloatPidget,
            editor_kwargs={
                "factory": pc.pidgets.FloatPidgetFactory(name_label_text="", limits=(0.0, 2.0)),
                "parent": None,
            },
            data_prototype=1.0,
            good_ui_edit=lambda fp: fp._spin_box.setValue(2.0),
            bad_ui_edit=lambda fp: fp._spin_box.setValue(-1.0),
            noop_ui_edit=lambda fp: fp._spin_box.setValue(1.0),
            read_ui=lambda fp: fp._spin_box.value(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.FloatSliderPidget,
            editor_kwargs={
                "factory": pc.pidgets.FloatSliderPidgetFactory(
                    name_label_text="", limits=(0.0, 2.0)
                ),
                "parent": None,
            },
            data_prototype=1.0,
            good_ui_edit=lambda fsp: fsp._slider.wrapped_set_value(2.0),
            bad_ui_edit=lambda fsp: fsp._slider.wrapped_set_value(-1.0),
            noop_ui_edit=lambda fsp: fsp._slider.wrapped_set_value(1.0),
            read_ui=lambda fsp: fsp._slider.value(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.OptionalFloatPidget,
            editor_kwargs={
                "factory": pc.pidgets.OptionalFloatPidgetFactory(name_label_text=""),
                "parent": None,
            },
            data_prototype=1.0,
            good_ui_edit=lambda ofp: ofp._spin_box.setValue(2.0),
            bad_ui_edit=lambda ofp: ofp._spin_box.setValue(-1.0),
            noop_ui_edit=lambda ofp: ofp._spin_box.setValue(1.0),
            read_ui=lambda ofp: ofp._spin_box.value(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.CheckboxPidget,
            editor_kwargs={
                "factory": pc.pidgets.CheckboxPidgetFactory(name_label_text=""),
                "parent": None,
            },
            data_prototype=True,
            good_ui_edit=lambda cbp: cbp._checkbox.click(),
            bad_ui_edit=lambda _: None,
            noop_ui_edit=lambda cbp: cbp._checkbox.setChecked(True),
            read_ui=lambda ofp: ofp._checkbox.isChecked(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.ComboboxPidget,
            editor_kwargs={
                "factory": pc.pidgets.ComboboxPidgetFactory(
                    name_label_text="",
                    items=[("1", 1), ("2", 2)],
                ),
                "parent": None,
            },
            data_prototype=1,
            good_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(1),
            bad_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(-1),
            noop_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(0),
            read_ui=lambda ofp: ofp._combobox.currentData(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.EnumPidget,
            editor_kwargs={
                "factory": pc.pidgets.EnumPidgetFactory(
                    name_label_text="",
                    enum_type=StubEnum,
                    label_mapping={StubEnum.A: "A", StubEnum.B: "B"},
                ),
                "parent": None,
            },
            data_prototype=StubEnum.A,
            good_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(1),
            bad_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(-1),
            noop_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(0),
            read_ui=lambda ofp: ofp._combobox.currentData(),
        ),
        EditorFixture(
            editor_class=pc.pidgets.OptionalEnumPidget,
            editor_kwargs={
                "factory": pc.pidgets.OptionalEnumPidgetFactory(
                    name_label_text="",
                    enum_type=StubEnum,
                    label_mapping={StubEnum.A: "A", StubEnum.B: "B"},
                ),
                "parent": None,
            },
            data_prototype=StubEnum.A,
            good_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(1),
            bad_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(-1),
            noop_ui_edit=lambda cbp: cbp._combobox.setCurrentIndex(0),
            read_ui=lambda ofp: ofp._combobox.currentData(),
        ),
    ],
    ids=lambda ef: str(ef.editor_class.__name__),
)
def pidget_editor_fixt(request: pytest.FixtureRequest) -> EditorFixture[t.Any]:
    return request.param  # type: ignore[no-any-return]


@pytest.fixture(params=["pidget_editor_fixt", "config_editor_fixt"])
def any_editor_fixt(
    request: pytest.FixtureRequest,
    pidget_editor_fixt: EditorFixture[t.Any],
    config_editor_fixt: EditorFixture[t.Any],
) -> EditorFixture[t.Any]:
    if request.param == "pidget_editor_fixt":
        return pidget_editor_fixt
    else:
        return config_editor_fixt


class TestSignalling:
    def test_setting_data_does_not_emit_sig_update(
        self, any_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = any_editor_fixt.get_editor()
        listener = Mock()
        editor.sig_update.connect(listener)

        editor.set_data(any_editor_fixt.data)
        listener.assert_not_called()

    def test_setting_data_via_ui_emits_sig_update(
        self, any_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = any_editor_fixt.get_editor()
        listener = Mock()
        editor.sig_update.connect(listener)

        any_editor_fixt.good_ui_edit(editor)
        listener.assert_called()

    def test_making_an_edit_signals_the_modified_object(
        self, any_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = any_editor_fixt.get_editor()
        original_data = editor.get_data()
        listener = Mock()
        editor.sig_update.connect(listener)

        any_editor_fixt.good_ui_edit(editor)
        (args, kwargs) = listener.call_args
        assert args != (original_data,)

    def test_making_an_bad_edit_signals_an_equal_object(
        self, config_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = config_editor_fixt.get_editor()
        original_data = editor.get_data()
        listener = Mock()
        editor.sig_update.connect(listener)

        config_editor_fixt.bad_ui_edit(editor)
        (args, kwargs) = listener.call_args
        assert args == (original_data,)

    def test_making_a_noop_edit_signals_an_equal_object(
        self, config_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = config_editor_fixt.get_editor()
        original_data = editor.get_data()
        listener = Mock()
        editor.sig_update.connect(listener)

        config_editor_fixt.noop_ui_edit(editor)
        listener.assert_called_once_with(original_data)

    def test_making_a_noop_edit_does_not_signal(
        self, pidget_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = pidget_editor_fixt.get_editor()
        listener = Mock()
        editor.sig_update.connect(listener)

        pidget_editor_fixt.noop_ui_edit(editor)
        listener.assert_not_called()


class TestState:
    def test_a_bad_edit_makes_the_editor_not_ready(
        self, config_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = config_editor_fixt.get_editor()

        assert editor.is_ready
        config_editor_fixt.bad_ui_edit(editor)
        assert not editor.is_ready

    def test_setting_data_to_None_disables(self, config_editor_fixt: EditorFixture[t.Any]) -> None:
        editor = config_editor_fixt.get_editor()

        editor.set_data(None)
        assert not editor.isEnabled()

    @pytest.mark.parametrize("enabled", [True, False])
    def test_calling_setEnabled_when_data_is_None_always_disables(
        self, config_editor_fixt: EditorFixture[t.Any], enabled: bool
    ) -> None:
        editor = config_editor_fixt.get_editor()

        editor.set_data(None)
        editor.setEnabled(enabled)
        assert not editor.isEnabled()

    def test_making_an_edit_changes_the_ui_value(
        self, any_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = any_editor_fixt.get_editor()

        original_value = any_editor_fixt.read_ui(editor)
        any_editor_fixt.good_ui_edit(editor)
        assert original_value != any_editor_fixt.read_ui(editor)

    def test_setting_data_changes_the_ui_value(
        self, any_editor_fixt: EditorFixture[t.Any]
    ) -> None:
        editor = any_editor_fixt.get_editor()

        any_editor_fixt.good_ui_edit(editor)
        original_value = any_editor_fixt.read_ui(editor)
        editor.set_data(any_editor_fixt.data)
        assert original_value != any_editor_fixt.read_ui(editor)
