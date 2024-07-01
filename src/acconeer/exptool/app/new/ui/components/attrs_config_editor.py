# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

import copy
from functools import partial
from typing import Any, Optional, Sequence, Type, TypeVar, Union, cast

import attrs

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool._core.entities.validation_result import Criticality, ValidationResult

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

    raise RuntimeError(
        "factory_mapping was neither a PidgetFactoryMappingi nor a PidgetGroupFactoryMapping"
    )


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
        extra_presenter: PresenterFunc = lambda i, t: None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent=parent)
        self._config = None
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(11)

        group_box = GroupBox.vertical(
            title,
            right_header=(
                create_json_save_load_buttons_from_type(
                    self, config_type, extra_presenter=extra_presenter
                )
                if save_load_buttons
                else None
            ),
            parent=self,
        )
        self.layout().addWidget(group_box)

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
