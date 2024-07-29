# Copyright (c) Acconeer AB, 2022-2024
# All rights reserved

from __future__ import annotations

from typing import Optional, Union

from PySide6 import QtCore
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool import a121
from acconeer.exptool.a121 import _core
from acconeer.exptool.app.new.ui.components.group_box import GroupBox


_WIDGET_WIDTH = 125


class SmartMetadataView(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self._layout = QVBoxLayout()
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.setLayout(self._layout)

        self._metadata_view = MetadataView(self)
        self._extended_metadata_view = ExtendedMetadataView(self)
        self._layout.addWidget(self._metadata_view)
        self._layout.addWidget(self._extended_metadata_view)

    def set_data(
        self,
        metadata: Optional[Union[a121.Metadata, list[dict[int, a121.Metadata]]]] = None,
    ) -> None:
        if isinstance(metadata, list):
            self._metadata_view.setHidden(True)
            self._extended_metadata_view.setHidden(False)
            self._extended_metadata_view.set_data(metadata)
        else:
            self._metadata_view.setHidden(False)
            self._extended_metadata_view.setHidden(True)
            self._metadata_view.set_data(metadata)


class ExtendedMetadataView(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setLayout(QVBoxLayout(self))

        group_box = GroupBox.vertical("Metadata", parent=self)
        self.layout().addWidget(group_box)

        self._tab_widget = QTabWidget(parent=self)
        self._tab_widget.setStyleSheet(
            """
            QTabWidget::pane { border: none; }
            * {margin: 0;}
            """
        )

        group_box.layout().addWidget(self._tab_widget)
        self._represent_none()

    def _represent_none(self) -> None:
        self._tab_widget.clear()
        self._add_needed_tabs(1)

    def _add_needed_tabs(self, needed_widgets: int) -> None:
        while self._tab_widget.count() < needed_widgets:
            subwidget = MetadataView(self)
            subwidget.setTitle("")
            self._tab_widget.addTab(subwidget, "-")

    def _remove_unnecessary_tabs(self, needed_widgets: int) -> None:
        while self._tab_widget.count() > needed_widgets:
            self._tab_widget.removeTab(0)

    def set_data(self, extended_metadata: Optional[list[dict[int, a121.Metadata]]]) -> None:
        if extended_metadata is None:
            self._represent_none()
            return

        tabs_needed = _core.utils.extended_structure_entry_count(extended_metadata)
        self._add_needed_tabs(tabs_needed)
        self._remove_unnecessary_tabs(tabs_needed)

        for i, (group_id, sensor_id, metadata) in enumerate(
            _core.utils.iterate_extended_structure(extended_metadata)
        ):
            self._tab_widget.setTabText(i, f"G{group_id}:S{sensor_id}")
            metadata_view = self._tab_widget.widget(i)
            if isinstance(metadata_view, MetadataView):
                metadata_view.set_data(metadata)
            else:
                msg = "ExtendedMetadataView contains child widgets that are not MetadataViews."
                raise RuntimeError(msg)


class MetadataView(QGroupBox):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        self.setTitle("Metadata")
        layout = QGridLayout(self)

        row = 0

        self.frame_data_length = MetadataValueWidget(self)
        layout.addWidget(self.frame_data_length, row, 1)

        frame_data_length_label = QLabel("Frame data length:", self)
        frame_data_length_label.setToolTip(a121.Metadata.frame_data_length.__doc__ or "")
        layout.addWidget(frame_data_length_label, row, 0)

        row += 1

        self.calibration_temperature = MetadataValueWidget(self)
        layout.addWidget(self.calibration_temperature, row, 1)

        calibration_temperature_label = QLabel("Calibration temperature:", self)
        calibration_temperature_label.setToolTip(
            a121.Metadata.calibration_temperature.__doc__ or ""
        )
        layout.addWidget(calibration_temperature_label, row, 0)

        row += 1

        self.max_sweep_rate = MetadataValueWidget(self)
        layout.addWidget(self.max_sweep_rate, row, 1)

        max_sweep_rate_label = QLabel("Max sweep rate:", self)
        max_sweep_rate_label.setToolTip(a121.Metadata.max_sweep_rate.__doc__ or "")
        layout.addWidget(max_sweep_rate_label, row, 0)

        row += 1

        self.high_speed_mode = MetadataValueWidget(self)
        layout.addWidget(self.high_speed_mode, row, 1)

        high_speed_mode_label = QLabel("High speed mode:", self)
        high_speed_mode_label.setToolTip(a121.Metadata.high_speed_mode.__doc__ or "")
        layout.addWidget(high_speed_mode_label, row, 0)

        self.setLayout(layout)
        self.set_data(None)

    def set_data(self, metadata: Optional[a121.Metadata]) -> None:
        self.frame_data_length.setText(f"{metadata.frame_data_length}" if metadata else "-")
        self.calibration_temperature.setText(
            f"{metadata.calibration_temperature}" if metadata else "-"
        )

        if metadata:
            if metadata.max_sweep_rate:
                max_sweep_rate_text = f"{metadata.max_sweep_rate:.0f} Hz"
            else:
                max_sweep_rate_text = "N/A"
        else:
            max_sweep_rate_text = "-"

        self.max_sweep_rate.setText(max_sweep_rate_text)

        self.high_speed_mode.setText(
            f"{metadata.high_speed_mode}"
            if metadata and metadata.high_speed_mode is not None
            else "-"
        )


class MetadataValueWidget(QLineEdit):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.setFixedWidth(_WIDGET_WIDTH)
        self.setReadOnly(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
