# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import enum
import typing as t

import pytest

from PySide6 import QtGui
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

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
            pidgets.EnumPidgetFactory: {"enum_type": enum.Enum, "label_mapping": {}},
            pidgets.OptionalEnumPidgetFactory: {"enum_type": enum.Enum, "label_mapping": {}},
            pidgets.ComboboxPidgetFactory: {"items": []},
            pidgets.ChoiceButtonsPidgetFactory: {"items": []},
            pidgets.PicturedFloatPidgetFactory: {"value_icon": lambda _: QtGui.QIcon()},
            pidgets.SensorIdPidgetFactory: {"items": []},
            pidgets.FloatSliderPidgetFactory: {"limits": (None, None)},
            pidgets.FloatRangeSliderPidgetFactory: {"limits": (None, None)},
            pidgets.OptionalFloatRangeSliderPidgetFactory: {"limits": (None, None)},
            pidgets.IntFlagPidgetFactory: {"num_bits": 1},
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
            pidgets.CollapsiblePidgetGroup: {"label": ":)", "collapsed": True}
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


@pytest.mark.usefixtures("qapplication")
class TestChoiceButtonsPidget:
    @pytest.fixture
    def pidget(self) -> t.Iterator[pidgets.ChoiceButtonsPidget[float]]:
        parent = QWidget()
        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Roll:",
            name_label_tooltip="Roll.",
            items=[("0°", 0.0), ("180°", 180.0)],
        )
        yield factory.create(parent)

    def _checked_texts(self, pidget: pidgets.ChoiceButtonsPidget[float]) -> list[str]:
        return [b.text() for b in pidget._buttons._button_group.buttons() if b.isChecked()]

    def test_set_data_checks_its_button_silently(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        pidget.set_data(180.0)

        assert self._checked_texts(pidget) == ["180°"]
        assert pidget.get_data() == 180.0
        assert updates == []

    def test_clicking_a_button_emits_its_value(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        pidget.set_data(0.0)
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        pidget._buttons._button_group.button(1).click()

        assert updates == [180.0]
        assert pidget.get_data() == 180.0

    def test_a_value_without_a_choice_checks_no_button(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        pidget.set_data(0.0)

        pidget.set_data(90.0)

        assert self._checked_texts(pidget) == []
        assert pidget.get_data() == 90.0

    def test_each_button_gets_the_icon_of_its_value(self) -> None:
        drawn: list[float] = []

        def icon(value: float) -> QtGui.QIcon:
            drawn.append(value)
            return QtGui.QIcon()

        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Roll:",
            name_label_tooltip="Roll.",
            items=[("0°", 0.0), ("180°", 180.0)],
            icon=icon,
        )
        factory.create(QWidget())

        assert drawn == [0.0, 180.0]

    def test_a_tooltip_mapping_not_matching_the_items_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="tooltip_mapping"):
            pidgets.ChoiceButtonsPidgetFactory(
                name_label_text="Roll:",
                name_label_tooltip="Roll.",
                items=[("0°", 0.0), ("180°", 180.0)],
                tooltip_mapping={0.0: "Upright."},
            )

    def test_custom_needs_number_choices(self) -> None:
        with pytest.raises(ValueError, match="custom"):
            pidgets.ChoiceButtonsPidgetFactory(
                name_label_text="Side:",
                name_label_tooltip="Side.",
                items=[("Left", "left"), ("Right", "right")],
                custom=pidgets.CustomChoice(limits=(0.0, 1.0), init_value=0.5, tooltip="Custom."),
            )

    def test_buttons_that_fit_take_the_width_of_the_other_widgets(self) -> None:
        pixmap = QtGui.QPixmap(8, 8)
        pixmap.fill()
        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Roll:",
            name_label_tooltip="Roll.",
            items=[("0°", 0.0), ("180°", 180.0)],
            icon=lambda _: QtGui.QIcon(pixmap),
            icon_size=(8, 8),
        )
        parent = QWidget()
        pidget = factory.create(parent)

        assert pidget._buttons.minimumSizeHint().width() < pidgets.WIDGET_WIDTH
        assert pidget._buttons.minimumWidth() == pidgets.WIDGET_WIDTH

    def test_buttons_wider_than_the_other_widgets_are_not_squeezed(self) -> None:
        panel = QWidget()
        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Pan:",
            name_label_tooltip="Pan.",
            items=[("Wall", 0.0), ("Left corner", -45.0), ("Right corner", 45.0)],
        )
        pidget = factory.create(panel)
        QVBoxLayout(panel).addWidget(pidget)
        # Narrower than the panel's contents want
        panel.resize(100, 100)
        panel.show()
        QApplication.processEvents()

        buttons = pidget._buttons._button_group.buttons()
        assert pidget._buttons.minimumSizeHint().width() > pidgets.WIDGET_WIDTH
        assert all(b.width() >= b.minimumSizeHint().width() for b in buttons)


@pytest.mark.usefixtures("qapplication")
class TestChoiceButtonsPidgetCustom:
    @pytest.fixture
    def drawn(self) -> list[float]:
        return []

    @pytest.fixture
    def pidget(self, drawn: list[float]) -> t.Iterator[pidgets.ChoiceButtonsPidget[float]]:
        def icon(value: float) -> QtGui.QIcon:
            drawn.append(value)
            return QtGui.QIcon()

        parent = QWidget()
        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Pan:",
            name_label_tooltip="Pan.",
            items=[("Wall", 0.0), ("Left corner", -45.0), ("Right corner", 45.0)],
            icon=icon,
            custom=pidgets.CustomChoice(limits=(-90.0, 90.0), init_value=20.0, tooltip="Custom."),
        )
        yield factory.create(parent)

    def _checked_texts(self, pidget: pidgets.ChoiceButtonsPidget[float]) -> list[str]:
        return [b.text() for b in pidget._buttons._button_group.buttons() if b.isChecked()]

    def _spin_box(self, pidget: pidgets.ChoiceButtonsPidget[float]) -> t.Any:
        return pidget._buttons._custom_spin_box

    def test_a_value_without_a_choice_shows_in_custom_silently(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        pidget.set_data(30.0)

        assert self._checked_texts(pidget) == ["Custom"]
        assert self._spin_box(pidget).value() == 30.0
        assert not self._spin_box(pidget).isHidden()
        assert pidget.get_data() == 30.0
        assert updates == []

    def test_clicking_custom_emits_its_value_and_shows_it(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        pidget.set_data(0.0)
        assert self._spin_box(pidget).isHidden()
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        pidget._buttons._button_group.button(3).click()

        assert updates == [20.0]
        assert not self._spin_box(pidget).isHidden()

    def test_editing_custom_emits_the_value(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        pidget.set_data(30.0)
        updates: list[t.Any] = []
        pidget.sig_update.connect(updates.append)

        self._spin_box(pidget).setValue(-10.0)

        assert updates == [-10.0]
        assert pidget.get_data() == -10.0

    def test_custom_stays_checked_at_a_choices_value(
        self, pidget: pidgets.ChoiceButtonsPidget[float]
    ) -> None:
        pidget.set_data(30.0)
        self._spin_box(pidget).setValue(45.0)

        # As the config editor sets each pidget's data after an edit.
        pidget.set_data(45.0)

        assert self._checked_texts(pidget) == ["Custom"]

    def test_a_choice_hides_custom(self, pidget: pidgets.ChoiceButtonsPidget[float]) -> None:
        pidget.set_data(30.0)

        pidget._buttons._button_group.button(0).click()

        assert self._checked_texts(pidget) == ["Wall"]
        assert self._spin_box(pidget).isHidden()
        assert pidget.get_data() == 0.0

    def test_custom_without_a_picture_shows_its_text(
        self, pidget: pidgets.ChoiceButtonsPidget[float], drawn: list[float]
    ) -> None:
        assert drawn == [0.0, -45.0, 45.0]
        assert pidget._buttons._custom_button.icon().isNull()

    def test_customs_picture_is_drawn_once(self) -> None:
        drawn: list[str] = []

        def icon() -> QtGui.QIcon:
            drawn.append("custom")
            return QtGui.QIcon()

        factory = pidgets.ChoiceButtonsPidgetFactory(
            name_label_text="Pan:",
            name_label_tooltip="Pan.",
            items=[("Wall", 0.0)],
            custom=pidgets.CustomChoice(
                limits=(-90.0, 90.0), init_value=20.0, tooltip="Custom.", icon=icon
            ),
        )
        parent = QWidget()
        pidget = factory.create(parent)

        pidget.set_data(30.0)
        pidget._buttons._custom_spin_box.setValue(-10.0)

        assert drawn == ["custom"]


@pytest.mark.usefixtures("qapplication")
class TestPicturedFloatPidget:
    @pytest.fixture
    def drawn(self) -> list[float]:
        return []

    @pytest.fixture
    def pidget(self, drawn: list[float]) -> t.Iterator[pidgets.PicturedFloatPidget]:
        def value_icon(value: float) -> QtGui.QIcon:
            drawn.append(value)
            return QtGui.QIcon()

        parent = QWidget()
        factory = pidgets.PicturedFloatPidgetFactory(
            name_label_text="Tilt:",
            name_label_tooltip="Tilt.",
            limits=(-45.0, 45.0),
            value_icon=value_icon,
        )
        yield factory.create(parent)

    def test_the_picture_is_drawn_once_per_set_data(
        self, pidget: pidgets.PicturedFloatPidget, drawn: list[float]
    ) -> None:
        pidget.set_data(20.0)

        assert drawn == [0.0, 20.0]

    def test_the_picture_follows_edits(
        self, pidget: pidgets.PicturedFloatPidget, drawn: list[float]
    ) -> None:
        pidget._spin_box.setValue(-10.0)

        assert drawn[-1] == -10.0
