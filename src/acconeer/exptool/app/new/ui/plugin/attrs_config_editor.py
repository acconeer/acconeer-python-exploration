from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

import attrs

from PySide6.QtWidgets import QVBoxLayout, QWidget

from acconeer.exptool.a121._core import Criticality

from .types import PidgetMapping
from .utils import VerticalGroupBox


T = TypeVar("T")


class AttrsConfigEditor(QWidget, Generic[T]):
    _config: Optional[T]

    def __init__(
        self, title: str, pidget_mapping: PidgetMapping, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent=parent)
        self._config = None
        self._pidget_mapping = pidget_mapping
        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(11)
        group_box = VerticalGroupBox(title, parent=self)
        self.layout().addWidget(group_box)

        for aspect, (pidget, f) in self._pidget_mapping.items():
            pidget.sig_parameter_changed.connect(
                lambda val: self._update_config_aspect(aspect, val if (f is None) else f(val))
            )
            group_box.layout().addWidget(pidget)

    @property
    def config(self) -> Optional[T]:
        return self._config

    @config.setter
    def config(self, config: Optional[T]) -> None:
        self._config = config
        self._update_pidgets()

    def _update_pidgets(self) -> None:
        if self._config is None:
            self.setEnabled(False)
            return

        self.setEnabled(True)
        for aspect, (pidget, _) in self._pidget_mapping.items():
            config_value = getattr(self._config, aspect)
            pidget.set_parameter(config_value)

    def _update_config_aspect(self, aspect: str, value: Any) -> None:
        if self._config is None:
            return

        try:
            attrs.evolve(self._config, **{aspect: value})
        except Exception as e:
            self._pidget_mapping[aspect][0].set_note_text(e.args[0], Criticality.ERROR)
