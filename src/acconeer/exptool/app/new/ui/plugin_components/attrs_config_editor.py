# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

from functools import partial
from typing import Any, Generic, Mapping, Optional, TypeVar

import attrs

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool import a121
from acconeer.exptool.a121._core import Criticality

from .pidgets import ParameterWidget
from .types import PidgetFactoryMapping
from .utils import VerticalGroupBox


T = TypeVar("T")


class AttrsConfigEditor(QWidget, Generic[T]):
    _config: Optional[T]

    sig_update = Signal(object)

    def __init__(
        self, title: str, factory_mapping: PidgetFactoryMapping, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)
        self._config = None
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(11)
        group_box = VerticalGroupBox(title, parent=self)
        self.layout().addWidget(group_box)

        self._pidget_mapping: Mapping[str, ParameterWidget] = {}

        for aspect, factory in factory_mapping.items():
            pidget = factory.create(group_box)
            pidget.sig_parameter_changed.connect(partial(self._update_config_aspect, aspect))
            group_box.layout().addWidget(pidget)

            self._pidget_mapping[aspect] = pidget

    def handle_validation_results(
        self, results: list[a121.ValidationResult]
    ) -> list[a121.ValidationResult]:
        for _, pidget in self._pidget_mapping.items():
            pidget.set_note_text("")

        unhandled_results: list[a121.ValidationResult] = []

        for result in results:
            if not self._handle_validation_result(result):
                unhandled_results.append(result)

        return unhandled_results

    def set_data(self, config: Optional[T]) -> None:
        self._config = config

    def sync(self) -> None:
        self._update_pidgets()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled and self._config is not None)

    def _broadcast(self) -> None:
        self.sig_update.emit(self._config)

    def _handle_validation_result(self, result: a121.ValidationResult) -> bool:
        if result.aspect is None:
            return False

        result_handled = False

        if result.source == self._config:
            for aspect, pidget in self._pidget_mapping.items():
                if result.aspect == aspect:
                    self._pidget_mapping[result.aspect].set_note_text(
                        result.message, result.criticality
                    )
                    result_handled = True

        return result_handled

    def _update_pidgets(self) -> None:
        if self._config is None:
            return

        for aspect, pidget in self._pidget_mapping.items():
            config_value = getattr(self._config, aspect)
            pidget.set_parameter(config_value)

    def _update_config_aspect(self, aspect: str, value: Any) -> None:
        if self._config is None:
            return

        try:
            self._config = attrs.evolve(self._config, **{aspect: value})
        except Exception as e:
            self._pidget_mapping[aspect].set_note_text(e.args[0], Criticality.ERROR)
        else:
            self._pidget_mapping[aspect].set_note_text(None)

        self._broadcast()
