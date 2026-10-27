# Copyright (c) Acconeer AB, 2026
# All rights reserved

from __future__ import annotations

from unittest.mock import Mock

import attrs
import pytest

from PySide6.QtCore import QCoreApplication, QEvent

from acconeer.exptool.app.new.ui.components import pidgets
from acconeer.exptool.app.new.ui.components.list_widget import ListWidget


pytestmark = pytest.mark.usefixtures("qapplication")


@attrs.frozen
class StubItem:
    value: int = attrs.field(default=0, validator=attrs.validators.ge(0))


def _make_widget() -> ListWidget[StubItem]:
    return ListWidget(
        title="Stub items",
        item_type=StubItem,
        item_factory_mapping={
            "value": pidgets.IntPidgetFactory(name_label_text="Value:", name_label_tooltip="tt"),
        },
        make_default_item=lambda: StubItem(0),
    )


class TestRowCount:
    def test_set_data_grows_rows(self) -> None:
        widget = _make_widget()

        widget.set_data([StubItem(1), StubItem(2), StubItem(3)])

        assert len(widget.get_data()) == 3

    def test_set_data_shrinks_rows(self) -> None:
        widget = _make_widget()

        widget.set_data([StubItem(1), StubItem(2), StubItem(3)])
        widget.set_data([StubItem(1)])

        assert len(widget.get_data()) == 1

    def test_set_data_grows_then_shrinks_then_grows(self) -> None:
        widget = _make_widget()

        widget.set_data([StubItem(1)])
        widget.set_data([StubItem(1), StubItem(2), StubItem(3)])
        widget.set_data([StubItem(1)])
        widget.set_data([StubItem(1), StubItem(2)])

        assert widget.get_data() == [StubItem(1), StubItem(2)]


class TestTeardown:
    def test_removing_the_last_row_of_an_unreferenced_widget(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1)])
        widget.set_data([])
        del widget

        # As the next event loop would: deletes the row, whose slots held the widget.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class TestSignalling:
    def test_setting_data_does_not_emit_sig_update(self) -> None:
        widget = _make_widget()
        listener = Mock()
        widget.sig_update.connect(listener)

        widget.set_data([StubItem(1), StubItem(2)])
        widget.set_data([StubItem(3)])
        widget.set_data([])

        listener.assert_not_called()

    def test_add_button_appends_a_row_and_emits(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1)])
        listener = Mock()
        widget.sig_update.connect(listener)

        widget._add_button.click()

        assert widget.get_data() == [StubItem(1), StubItem(0)]
        listener.assert_called_once_with([StubItem(1), StubItem(0)])

    def test_remove_button_removes_its_row_and_emits(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1), StubItem(2)])
        listener = Mock()
        widget.sig_update.connect(listener)

        (_, remove_button, _) = widget._rows[0]
        remove_button.click()

        assert widget.get_data() == [StubItem(2)]
        listener.assert_called_once_with([StubItem(2)])


class TestRowIdentityStability:
    def test_row_widget_id_is_stable_across_unchanged_length_set_data(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1), StubItem(2)])
        (_, _, row_widget_before) = widget._rows[0]

        widget.set_data([StubItem(1), StubItem(2)])

        (_, _, row_widget_after) = widget._rows[0]
        assert id(row_widget_before) == id(row_widget_after)

    def test_typed_but_uncommitted_text_survives_unrelated_broadcast(self) -> None:
        """This is the direct regression test for F1.

        A broadcast that re-delivers the same (unchanged) data must not
        rebuild the row the user is actively typing into.
        """
        widget = _make_widget()
        widget.set_data([StubItem(1), StubItem(2)])

        (row_editor, _, _) = widget._rows[0]
        spin_box = row_editor._pidget_mapping["value"]._spin_box
        spin_box.lineEdit().setText("12")

        # Simulate an unrelated broadcast redelivering the same data.
        widget.set_data([StubItem(1), StubItem(2)])

        assert spin_box.lineEdit().text() == "12"


class TestReadiness:
    def test_is_ready_when_all_rows_are_valid(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1), StubItem(2)])

        assert widget.is_ready

    def test_is_not_ready_when_a_row_is_invalid(self) -> None:
        widget = _make_widget()
        widget.set_data([StubItem(1)])

        (row_editor, _, _) = widget._rows[0]
        row_editor._update_config_aspect("value", -1)

        assert not widget.is_ready
