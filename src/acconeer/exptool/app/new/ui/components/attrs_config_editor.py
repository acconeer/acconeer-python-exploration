# Copyright (c) Acconeer AB, 2022-2025
# All rights reserved

from __future__ import annotations

import copy
import itertools
from functools import partial
from typing import (
    Any,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    cast,
)

import attrs

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool._core.entities.validation_result import Criticality, ValidationResult
from acconeer.exptool.app.new.ui.components.overlay import Overlay
from acconeer.exptool.app.new.ui.utils import LayoutWrapper

from .data_editor import DataEditor
from .group_box import GroupBox
from .json_save_load_buttons import (
    JsonPresentable,
    PresenterFunc,
    create_json_save_load_buttons_from_type,
)
from .pidgets import FlatPidgetGroup, Pidget, PidgetGroup, PidgetHook, WidgetHook
from .types import PidgetFactoryMapping, PidgetGroupFactoryMapping


T = TypeVar("T", bound=JsonPresentable)


def _to_group_factory_mapping(
    factory_mapping: Union[PidgetFactoryMapping, PidgetGroupFactoryMapping],
) -> PidgetGroupFactoryMapping:
    if factory_mapping == {}:
        return {}

    (first_key, *_) = factory_mapping

    # The casts boils down to "non-transferable" type narrowing
    # of a Mapping (typically a dict) given its keys.
    #   In this function, we want to do type narrowing of the parameter type
    # (rewritten as dict[Union[str, PidgetGroup], ...]). The key will have type
    # Union[str, PidgetGroup], which can be narrowed to str or PidgetGroup.
    # This type narrowing is not transferred to the original dict, requiring a cast.
    if isinstance(first_key, PidgetGroup):
        return cast(PidgetGroupFactoryMapping, factory_mapping)

    if isinstance(first_key, str):
        return {FlatPidgetGroup(): cast(PidgetFactoryMapping, factory_mapping)}

    msg = "factory_mapping was neither a PidgetFactoryMappingi nor a PidgetGroupFactoryMapping"
    raise RuntimeError(msg)


class AttrsConfigEditor(DataEditor[Optional[T]]):
    _config: Optional[T]
    _erroneous_aspects: set[str]

    sig_update = Signal(object)

    def __init__(
        self,
        title: str,
        factory_mapping: Union[PidgetFactoryMapping, PidgetGroupFactoryMapping],
        config_type: Type[T],
        *,
        save_load_buttons: bool = True,
        min_top_padding: int = 0,
        extra_presenter: PresenterFunc = lambda i, t: None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)
        self._config = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(11)

        group_box = GroupBox.vertical(
            title,
            right_header=(
                create_json_save_load_buttons_from_type(
                    self, config_type, extra_presenter=extra_presenter
                )
                if save_load_buttons
                else None
            ),
            min_top_padding=min_top_padding,
            parent=self,
        )
        layout.addWidget(group_box)

        self._pidget_mapping: dict[str, Pidget] = {}
        self._pidget_hooks: dict[str, Sequence[PidgetHook]] = {}
        self._group_widgets: list[QWidget] = []
        self._group_hooks: list[Sequence[WidgetHook]] = []
        self._erroneous_aspects = set()

        for pidget_group, factory_mapping in _to_group_factory_mapping(factory_mapping).items():
            pidgets = []
            for aspect, factory in factory_mapping.items():
                pidget = factory.create(group_box)
                pidget.sig_update.connect(partial(self._update_config_aspect, aspect))

                self._pidget_mapping[aspect] = pidget
                self._pidget_hooks[aspect] = factory.hooks

                pidgets.append(pidget)

            group_widget = pidget_group.get_container(pidgets)
            group_box.layout().addWidget(group_widget)

            self._group_widgets.append(group_widget)
            self._group_hooks.append(pidget_group.hooks)

        self.setLayout(layout)

    def set_data(self, config: Optional[T]) -> None:
        if self._config == config:
            return

        self._config = config
        self.setEnabled(config is not None)

        if self._config is None:
            return

        for aspect, pidget in self._pidget_mapping.items():
            if aspect in self._erroneous_aspects:
                continue
            config_value = getattr(self._config, aspect)
            pidget.set_data(config_value)

        for aspect, hooks in self._pidget_hooks.items():
            for hook in hooks:
                hook(self._pidget_mapping[aspect], self._pidget_mapping)

        for group_widget, hooks in zip(self._group_widgets, self._group_hooks):
            for hook in hooks:
                hook(group_widget, self._pidget_mapping)

    def get_data(self) -> Optional[T]:
        return copy.deepcopy(self._config)

    def handle_validation_results(self, results: list[ValidationResult]) -> list[ValidationResult]:
        for aspect, pidget in self._pidget_mapping.items():
            if aspect not in self._erroneous_aspects:
                pidget.set_note_text("")

        unhandled_results: list[ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        return unhandled_results

    @property
    def is_ready(self) -> bool:
        return self._erroneous_aspects == set()

    def _handle_validation_result(self, result: ValidationResult) -> bool:
        if result.aspect is None:
            return False

        if result.aspect in self._erroneous_aspects:
            # If there is an erroneous aspect in the GUI, we do not want to overwrite that.
            # Once the erroneous aspect is handled with, the same validation result will
            # come through here anyway
            return True

        result_handled = False

        if result.source == self._config:
            for aspect, pidget in self._pidget_mapping.items():
                if result.aspect == aspect:
                    self._pidget_mapping[result.aspect].set_note_text(
                        result.message, result.criticality
                    )
                    result_handled = True

        return result_handled

    def _update_config_aspect(self, aspect: str, value: Any) -> None:
        if self._config is None:
            return

        try:
            # The passing of "self._config: T" is not type safe. We cannot know
            # if "T" is an attrs class in the scope of this class without binding
            # "T" to a common superclass.
            # "AlgoConfigBase" is a candidate, but that is part of the algo-package.
            config = attrs.evolve(self._config, **{aspect: value})  # type: ignore[misc]
        except Exception as e:
            self._erroneous_aspects.add(aspect)
            self._pidget_mapping[aspect].set_note_text(e.args[0], Criticality.ERROR)

            # this emit needs to be done to signal that "is_ready" has changed.
            self.sig_update.emit(self.get_data())
        else:
            self._pidget_mapping[aspect].set_note_text(None)
            self._erroneous_aspects.discard(aspect)

            self.set_data(config)
            self.sig_update.emit(config)

    def set_pidget_enabled(self, aspect: str, enabled: bool) -> None:
        if (pidget := self._pidget_mapping.get(aspect)) is None:
            return
        pidget.setEnabled(enabled)


class JoinedPartialAttrsConfigEditors(DataEditor[Optional[T]]):
    """
    A Partial Editor is a pattern that has emerged where
    an ``AttrsConfigEditor`` is constructed with an ``PidgetFactoryMapping``
    that doesn't fully cover all the fields of a config.

    For example: say you want an editor for the following object

        @attrs.mutable
        class Person:
            age: int
            height: int

    Then you might have an editor that looks something like this:

        +- Person physical properties --|S| |L|-+
        |                                       |
        |  Age:                     |_____25_|  |
        |  Height:                  |____170_|  |
        +---------------------------------------+

    with the corresponding pidget mapping

        {"age": IntPidgetFactory(...), "height": IntPidgetFactory(...)}


    This is what the ``AttrsConfigEditor`` class is used for and it also
    supports the save-/load buttons (denoted |S| & |L|).

    However, if now a field like ``favorite_number: int`` was added to the ``Person`` class.
    A field like that doesn't fit the category "physical properties" so you would like to
    separate them visually and have the values stored in the same logical place (the ``Person`` class):

        +- Person physical properties --|S| |L|-+
        |                                       |
        |  Age:                     |_____25_|  |
        |  Height:                  |____170_|  |
        +---------------------------------------+
        +- Person fun facts --------------------+
        |                                       |
        |  Favorite number:         |______7_|  |
        +---------------------------------------+

    The sketch shows 2 partial editors of ``Person``s and that is what this class is used for.
    Programmatically, creating one looks something like this:

        JoinedPartialAttrsConfigEditors(
            {"Person physical properties": {"age": IntPidgetFactory(...), "height": IntPidgetFactory(...)},
             "Person fun facts": {"favorite_number": IntPidgetFactory(...)}},
        )

    The implementation makes sure that set_data/get_data propagates/joins the information
    from each partial widget correctly and also that the save-/load buttons behave as expected.
    """

    def __init__(
        self,
        editor_kwargs: dict[str, Union[PidgetFactoryMapping, PidgetGroupFactoryMapping]],
        config_type: type[T],
        save_load_buttons: bool = True,
        extra_presenter: PresenterFunc = lambda i, t: None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)

        if len(editor_kwargs) < 2:
            msg = f"Need to pass at least 2 'editor_kwargs'. Passed {len(editor_kwargs)}"
            raise ValueError(msg)

        self._editor_aspects = tuple(
            frozenset(mapping.keys())
            for group in map(_to_group_factory_mapping, editor_kwargs.values())
            for mapping in group.values()
        )

        for a, b in itertools.combinations(self._editor_aspects, 2):
            if intersec := a.intersection(b):
                msg = f"Pidget factory mappings needs to be disjoint. Found duplicates {intersec}"
                raise ValueError(msg)

        if save_load_buttons:
            buttons = create_json_save_load_buttons_from_type(
                self, config_type, extra_presenter=extra_presenter
            )
            assert buttons is not None
            min_top_padding = buttons.sizeHint().height() // 2
        else:
            buttons = None
            min_top_padding = 0

        self._editors = tuple(
            AttrsConfigEditor(
                title=title,
                factory_mapping=mapping,
                config_type=config_type,
                save_load_buttons=False,
                min_top_padding=min_top_padding if i == 0 else 0,
                extra_presenter=extra_presenter,
            )
            for i, (title, mapping) in enumerate(editor_kwargs.items())
        )

        for editor in self._editors:
            editor.sig_update.connect(lambda _: self.sig_update.emit(self.get_data()))

        editor_layout = QVBoxLayout()
        for editor in self._editors:
            editor_layout.addWidget(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        if buttons is None:
            self.setLayout(editor_layout)
        else:
            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(
                Overlay(
                    base=LayoutWrapper(editor_layout),
                    overlays=[(buttons, Overlay.positioner_top_right)],
                )
            )
            self.setLayout(layout)

    def get_data(self) -> Optional[T]:
        (head_editor, *tail_editors) = self._editors
        (_, *tail_editor_aspects) = self._editor_aspects

        instance = head_editor.get_data()
        if instance is None:
            return None

        for editor, aspects in zip(tail_editors, tail_editor_aspects):
            partial = editor.get_data()
            if partial is None:
                return None

            changes = {asp: getattr(partial, asp) for asp in aspects}
            instance = attrs.evolve(instance, **changes)  # type: ignore[misc]

        return instance

    def set_data(self, data: Optional[T]) -> None:
        for editor in self._editors:
            editor.set_data(data)

    def set_pidget_enabled(self, aspect: str, enabled: bool) -> None:
        for editor in self._editors:
            editor.set_pidget_enabled(aspect, enabled)

    def handle_validation_results(self, results: list[ValidationResult]) -> list[ValidationResult]:
        not_handled = results
        for editor in self._editors:
            not_handled = editor.handle_validation_results(not_handled)
        return not_handled

    @property
    def is_ready(self) -> bool:
        return all([editor.is_ready for editor in self._editors])
