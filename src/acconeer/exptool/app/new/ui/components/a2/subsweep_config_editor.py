# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved
from __future__ import annotations

import typing as t

import numpy as np

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from acconeer.exptool import a2
from acconeer.exptool._core.docstrings import get_attribute_docstring
from acconeer.exptool.a2._core.entities.configs import subsweep_config
from acconeer.exptool.app.new.ui import icons
from acconeer.exptool.app.new.ui.components.attrs_config_editor import AttrsConfigEditor
from acconeer.exptool.app.new.ui.components.data_editor import DataEditor
from acconeer.exptool.app.new.ui.components.pidgets import pidgets
from acconeer.exptool.app.new.ui.components.pidgets.hooks import (
    disable_if,
    parameter_equals,
)
from acconeer.exptool.app.new.ui.components.range_help_view import RangeHelpView
from acconeer.exptool.app.new.ui.components.types import PidgetFactoryMapping


def range_factory_mapping() -> PidgetFactoryMapping:
    return {
        "start_point": pidgets.IntPidgetFactory(
            name_label_text="Start point:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "start_point"),
            limits=(subsweep_config.MIN_START_POINT, subsweep_config.MAX_START_POINT),
        ),
        "num_points": pidgets.IntPidgetFactory(
            name_label_text="Number of points:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "num_points"),
            limits=(subsweep_config.MIN_NUM_POINTS, subsweep_config.MAX_NUM_POINTS),
        ),
        "step_length": pidgets.IntPidgetFactory(
            name_label_text="Step length:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "step_length"),
            limits=(subsweep_config.MIN_STEP_LENGTH, subsweep_config.MAX_STEP_LENGTH),
        ),
    }


def hwaas_factory_mapping(
    extra_widget_factory: t.Callable[[], t.Optional[QWidget]] = lambda: None,
) -> PidgetFactoryMapping:
    return {
        "hwaas_max": pidgets.IntPidgetFactory(
            name_label_text="HWAAS max:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "hwaas_max"),
            limits=(subsweep_config.MIN_HWAAS, subsweep_config.MAX_HWAAS),
            extra_widget_factory=extra_widget_factory,
        ),
        "hwaas_min": pidgets.IntPidgetFactory(
            name_label_text="HWAAS min:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "hwaas_min"),
            limits=(subsweep_config.MIN_HWAAS, subsweep_config.MAX_HWAAS),
            hooks=disable_if(parameter_equals("hwaas_exponent", 0)),
            extra_widget_factory=extra_widget_factory,
        ),
        "hwaas_exponent": pidgets.IntPidgetFactory(
            name_label_text="HWAAS exp:",
            name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "hwaas_exponent"),
            limits=(subsweep_config.MIN_HWAAS_EXPONENT, subsweep_config.MAX_HWAAS_EXPONENT),
            extra_widget_factory=extra_widget_factory,
        ),
    }


class _QDialogThatIgnoresReturn(QDialog):
    def keyPressEvent(self, arg__1: QKeyEvent) -> None:
        if arg__1.key() == Qt.Key.Key_Return:
            return
        super().keyPressEvent(arg__1)


class SubsweepConfigEditor(DataEditor[t.Optional[a2.SubsweepConfig]]):
    def __init__(self) -> None:
        super().__init__()
        self._range_help_view = RangeHelpView()
        self._attrs_config_editor = _SubsweepAttrsConfigEditor(
            range_help_view_widget=self._range_help_view
        )

        self._attrs_config_editor.sig_update.connect(self.sig_update.emit)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._attrs_config_editor)
        # The RangeHelpView is NOT added to the layout here
        # as it is part of the AttrsConfigEditor's header layout.

        self.setLayout(layout)

    def set_data(self, data: t.Optional[a2.SubsweepConfig]) -> None:
        self._range_help_view.set_data(data)
        self._attrs_config_editor.set_data(data)

    def get_data(self) -> t.Optional[a2.SubsweepConfig]:
        return self._attrs_config_editor.get_data()

    def handle_validation_results(
        self, validation_results: list[a2.ValidationResult]
    ) -> list[a2.ValidationResult]:
        return self._attrs_config_editor.handle_validation_results(validation_results)

    @property
    def is_ready(self) -> bool:
        return self._attrs_config_editor.is_ready


class _SubsweepAttrsConfigEditor(AttrsConfigEditor[a2.SubsweepConfig]):
    def __init__(self, range_help_view_widget: RangeHelpView) -> None:
        super().__init__(
            title="Subsweep parameters",
            header_widgets=[range_help_view_widget],
            factory_mapping={
                **range_factory_mapping(),
                "profile": pidgets.EnumPidgetFactory(
                    name_label_text="Profile:",
                    name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "profile"),
                    enum_type=a2.Profile,
                    label_mapping={
                        a2.Profile.PROFILE_1: "1",
                        a2.Profile.PROFILE_2: "2",
                        a2.Profile.PROFILE_3: "3",
                        a2.Profile.PROFILE_4: "4",
                        a2.Profile.PROFILE_5: "5",
                        a2.Profile.PROFILE_6: "6",
                        a2.Profile.PROFILE_7: "7",
                    },
                ),
                "prf": pidgets.EnumPidgetFactory(
                    name_label_text="PRF:",
                    name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "prf"),
                    enum_type=a2.PRF,
                    label_mapping={
                        a2.PRF.PRF_5_3_MHZ: "5.3 MHz",
                        a2.PRF.PRF_8_3_MHZ: "8.3 MHz",
                        a2.PRF.PRF_12_5_MHZ: "12.5 MHz",
                        a2.PRF.PRF_15_8_MHZ: "15.8 MHz",
                        a2.PRF.PRF_20_8_MHZ: "20.8 MHz",
                        a2.PRF.PRF_27_7_MHZ: "27.7 MHz",
                    },
                ),
                "tx_antenna_mask": pidgets.IntFlagPidgetFactory(
                    name_label_text="Tx antenna mask:",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SubsweepConfig, "tx_antenna_mask"
                    ),
                    num_bits=3,
                ),
                "rx_antenna_mask": pidgets.IntFlagPidgetFactory(
                    name_label_text="Rx antenna mask:",
                    name_label_tooltip=get_attribute_docstring(
                        a2.SubsweepConfig, "rx_antenna_mask"
                    ),
                    num_bits=4,
                ),
                **hwaas_factory_mapping(self.create_hwaas_info_button),
                "receiver_gain": pidgets.IntPidgetFactory(
                    name_label_text="Receiver gain:",
                    name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "receiver_gain"),
                    limits=(
                        subsweep_config.MIN_RECEIVER_GAIN,
                        subsweep_config.MAX_RECEIVER_GAIN,
                    ),
                ),
                "enable_tx": pidgets.CheckboxPidgetFactory(
                    name_label_text="Enable transmitter",
                    name_label_tooltip=get_attribute_docstring(a2.SubsweepConfig, "enable_tx"),
                ),
            },
            config_type=a2.SubsweepConfig,
        )

    def create_hwaas_info_button(self) -> QWidget:
        button = QToolButton()
        button.setIcon(icons.HELP())
        button.setFixedWidth(30)
        button.clicked.connect(lambda: self._hwaas_popup(self.get_data()))
        return button

    def _hwaas_popup(self, config: t.Optional[a2.SubsweepConfig]) -> None:
        if config is None:
            return

        configette_editor = AttrsConfigEditor(
            title="Parameters affecting HWAAS",
            factory_mapping={
                **range_factory_mapping(),
                **hwaas_factory_mapping(),
            },
            config_type=a2.SubsweepConfig,
            save_load_buttons=False,
        )
        configette_editor.set_data(config)

        chart_widget = QChartView()
        chart_widget.setMinimumSize(500, 500)
        chart = chart_widget.chart()
        chart.setAnimationOptions(QChart.AnimationOption.SeriesAnimations)

        x_axis = QValueAxis()
        x_axis.setTitleText("Measured distance (m)")
        chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)

        snr_axis = QValueAxis()
        snr_axis.setTitleText("Relative SNR")
        chart.addAxis(snr_axis, Qt.AlignmentFlag.AlignLeft)

        hwaas_axis = QValueAxis()
        hwaas_axis.setTitleText("HWAAS")
        hwaas_axis.setLabelFormat("%d")
        chart.addAxis(hwaas_axis, Qt.AlignmentFlag.AlignRight)

        hwaas_series = QLineSeries()
        chart.addSeries(hwaas_series)
        hwaas_series.setName("HWAAS")
        pen = hwaas_series.pen()
        pen.setWidth(4)
        hwaas_series.setPen(pen)
        hwaas_series.attachAxis(x_axis)
        hwaas_series.attachAxis(hwaas_axis)

        generic_snr_series = QLineSeries()
        chart.addSeries(generic_snr_series)
        generic_snr_series.setName("Rel. SNR of generic objects")
        pen = generic_snr_series.pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        generic_snr_series.setPen(pen)
        generic_snr_series.attachAxis(x_axis)
        generic_snr_series.attachAxis(snr_axis)

        planar_snr_series = QLineSeries()
        chart.addSeries(planar_snr_series)
        planar_snr_series.setName("Rel. SNR of planar objects")
        pen = planar_snr_series.pen()
        pen.setStyle(Qt.PenStyle.DotLine)
        planar_snr_series.setPen(pen)
        planar_snr_series.attachAxis(x_axis)
        planar_snr_series.attachAxis(snr_axis)

        def update_hwaas_plot(config: a2.SubsweepConfig) -> None:
            hwaas_series.clear()
            generic_snr_series.clear()
            planar_snr_series.clear()

            if config.num_points == 0:
                return

            distances_p = config.start_point + np.arange(config.num_points) * config.step_length
            d_end = distances_p[-1]

            if len(distances_p) == 1:
                hwaases = np.array([config.hwaas_max])
            elif d_end <= 0 or config.hwaas_exponent == 0:
                hwaases = np.full_like(distances_p, config.hwaas_max)
            else:
                hwaases = np.vectorize(
                    lambda d_n: (
                        config.hwaas_min
                        if d_n <= 0
                        else max(
                            config.hwaas_min,
                            int(config.hwaas_max * (d_n / d_end) ** config.hwaas_exponent),
                        )
                    )
                )(distances_p)

            distances_m = distances_p * 2.5e-3
            x_axis.setRange(min(distances_m), max(distances_m))

            for d, hwaas in zip(distances_m, hwaases):
                hwaas_series.append(d, hwaas)

            some_powers_of_2 = 2 ** np.arange(6, 20)
            y_max = some_powers_of_2[sum(some_powers_of_2 < max(hwaases))]
            hwaas_axis.setRange(0, y_max)

            if (distances_m > 0).any():
                snr_distances = distances_m[distances_m > 0]
                snr_hwaases = hwaases[distances_m > 0]
                snr_hwaases_db = 10 * np.log10(snr_hwaases)

                generic_relative_snrs = 10 * np.log10((snr_distances[0] / snr_distances) ** 4)
                generic_snrs = snr_hwaases_db + generic_relative_snrs
                generic_snrs -= generic_snrs[0]

                for d, snr in zip(snr_distances, generic_snrs):
                    generic_snr_series.append(d, snr)

                planar_relative_snrs = 10 * np.log10((snr_distances[0] / snr_distances) ** 2)
                planar_snrs = snr_hwaases_db + planar_relative_snrs
                planar_snrs -= planar_snrs[0]

                for d, snr in zip(snr_distances, planar_snrs):
                    planar_snr_series.append(d, snr)

                y_steps = -(20 * np.arange(20))
                y_min = min(
                    y_steps[sum(y_steps > min(generic_snrs))],
                    y_steps[sum(y_steps > min(planar_snrs))],
                )

                y_max = max(generic_snrs.max(), planar_snrs.max())
                snr_axis.setRange(y_min, y_max)

        configette_editor.sig_update.connect(update_hwaas_plot)
        update_hwaas_plot(config)  # initial trigger to show curve first time

        dialog = _QDialogThatIgnoresReturn()
        dialog.setWindowTitle("Hardware Accelerated Average Samples")
        dialog.setWindowFlags(Qt.WindowType.Window)
        dialog.setSizeGripEnabled(True)
        button_box = QDialogButtonBox()
        button_box.setStandardButtons(
            QDialogButtonBox.StandardButton.Close
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Reset
        )

        button_box.clicked.connect(
            lambda btn: (
                self.set_data(configette_editor.get_data())
                if button_box.buttonRole(btn) == QDialogButtonBox.ButtonRole.ApplyRole
                else None
            )
        )
        initial_config = config
        button_box.clicked.connect(
            lambda btn: (
                configette_editor.set_data(initial_config)
                if button_box.buttonRole(btn) == QDialogButtonBox.ButtonRole.ResetRole
                else None
            )
        )
        button_box.clicked.connect(
            lambda btn: (
                update_hwaas_plot(initial_config)
                if button_box.buttonRole(btn) == QDialogButtonBox.ButtonRole.ResetRole
                else None
            )
        )

        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        info_text = QTextEdit()
        info_text.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        info_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        info_text.setReadOnly(True)
        info_text.setMinimumSize(dialog.minimumSize() * 0.5)
        info_text.setText(
            """
<h3 align=center>Hardware Accelerated Average Samples</h3>
<p>
HWAAS decides how many times each distance point is sampled.
The sensor hardware produces an average value of those samples.
</p>
<p>
The time needed to measure a sweep is roughly proportional
to the number of HWAAS. Hence, if there is a need to obtain a higher update
rate, HWAAS could be decreased but this leads to lower SNR.
</p>

<h4 align=center>Scaling of HWAAS</h4>

<p>The <code>hwaas_exponent</code> parameter controls how HWAAS is scaled with respect to distance during a sweep.
The scaling is determined by the formula:</p>

<code>max(hwaas_min, hwaas_max * (d_n / d_end) ^ hwaas_exponent)</code>

<p>where <code>d_n</code> is the distance at point <code>n</code> and <code>d_end</code> is the distance at the last point in the sweep.</p>

<p>HWAAS-scaling compensates for the energy loss of the propagating signal as it travels to and from the target.</p>

<h4 align=center>Commonly used exponent values</h4>
<table margin-top=5px>
    <tr><th>Exponent</th><th>Description</th></tr>
    <tr><td align=center>4</td><td>Use this for targets with a general shape. This accounts for the highest degree of energy dilution.</td></tr>
    <tr><td align=center>2</td><td>Use this for large planar targets, such as flat surfaces, where energy spreads less.</td></tr>
    <tr><td align=center>0</td><td>Use this to maintain constant HWAAS throughout the sweep. No scaling is applied, and HWAAS remains unchanged.</td></tr>
</table>
"""
        )

        layout = QGridLayout()
        layout.addWidget(chart_widget, 0, 0, 2, 1)
        layout.addWidget(configette_editor, 0, 1, 1, 1)
        layout.addWidget(info_text, 1, 1, 1, 1)
        layout.addWidget(button_box, 2, 0, 1, -1)
        layout.setRowStretch(1, 1)

        dialog.setLayout(layout)
        dialog.exec()
