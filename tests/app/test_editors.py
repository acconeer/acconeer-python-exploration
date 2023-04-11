# Copyright (c) Acconeer AB, 2023
# All rights reserved

from __future__ import annotations

import copy
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
    good_ui_edit: t.Callable[[pc.DataEditor[T]], None]
    bad_ui_edit: t.Callable[[pc.DataEditor[T]], None]
    read_ui: t.Callable[[pc.DataEditor[T]], t.Any]
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
            read_ui=lambda ace: ace._pidget_mapping["a"].get_parameter(),
        ),
        EditorFixture(
            editor_class=pc.SessionConfigEditor,
            data_prototype=a121.SessionConfig(),
            good_ui_edit=partial(pc.SessionConfigEditor._update_update_rate, value=1.0),
            bad_ui_edit=partial(pc.SessionConfigEditor._update_update_rate, value=-1.0),
            read_ui=lambda sce: sce._update_rate_pidget.get_parameter(),
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
            read_ui=lambda sce: sce._sensor_config_pidgets["frame_rate"].get_parameter(),
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
            read_ui=lambda sce: sce._subsweep_config_pidgets["hwaas"].get_parameter(),
        ),
    ],
    ids=lambda ef: str(ef.editor_class.__name__),
)
def editor_fixture(request: pytest.FixtureRequest) -> EditorFixture[t.Any]:
    return request.param  # type: ignore[no-any-return]


class TestSignalling:
    def test_setting_data_does_not_emit_sig_update(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()
        listener = Mock()
        editor.sig_update.connect(listener)

        editor.set_data(editor_fixture.data)
        listener.assert_not_called()

    def test_setting_data_via_ui_emits_sig_update(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()
        listener = Mock()
        editor.sig_update.connect(listener)

        editor_fixture.good_ui_edit(editor)
        listener.assert_called()


class TestState:
    def test_a_bad_edit_makes_the_editor_not_ready(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()

        assert editor.is_ready
        editor_fixture.bad_ui_edit(editor)
        assert not editor.is_ready

    def test_setting_data_to_None_does_not_disable_even_after_sync(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()

        editor.set_data(None)
        assert editor.isEnabled()
        editor.sync()
        assert editor.isEnabled()

    @pytest.mark.parametrize("enabled", [True, False])
    def test_calling_setEnabled_when_data_is_None_always_disables(
        self, editor_fixture: EditorFixture[t.Any], enabled: bool
    ) -> None:
        editor = editor_fixture.get_editor()

        editor.set_data(None)
        editor.setEnabled(enabled)
        assert not editor.isEnabled()

    def test_making_an_edit_does_not_change_the_ui_value(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()

        original_value = editor_fixture.read_ui(editor)
        editor_fixture.good_ui_edit(editor)
        assert original_value == editor_fixture.read_ui(editor)

    def test_setting_data_does_not_change_the_ui_value(
        self, editor_fixture: EditorFixture[t.Any]
    ) -> None:
        editor = editor_fixture.get_editor()

        editor_fixture.good_ui_edit(editor)
        original_value = editor_fixture.read_ui(editor)
        editor.set_data(editor_fixture.data)
        assert original_value == editor_fixture.read_ui(editor)
