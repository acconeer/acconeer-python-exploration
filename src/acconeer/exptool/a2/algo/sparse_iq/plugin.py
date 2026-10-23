# Copyright (c) Acconeer AB, 2023-2026
# All rights reserved

from __future__ import annotations

import itertools
import logging
import platform
import typing as t

import attrs
import h5py
import numpy as np
import numpy.typing as npt

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QPushButton, QVBoxLayout

import pyqtgraph as pg

import acconeer.exptool as et
import acconeer.exptool.a2._core.channel_convention as ch_conv
import acconeer.exptool.a2.algo._utils as algo_utils
from acconeer.exptool import a2
from acconeer.exptool._core.entities.validation_result import ValidationResult
from acconeer.exptool.a2._core.entities import Metadata
from acconeer.exptool.a2.algo._plugin_specs.sparse_iq import PluginPresetId
from acconeer.exptool.a2.algo._plugins import A2BackendPluginBase, A2ViewPluginBase
from acconeer.exptool.app.new import (
    AppModel,
    GeneralMessage,
    MiscErrorView,
    PlotPluginBase,
    backend,
    is_task,
    visual_policies,
)
from acconeer.exptool.app.new.ui import GroupBox, icons
from acconeer.exptool.app.new.ui.components import GotoResourceTabButton, TabPGWidget
from acconeer.exptool.app.new.ui.components.a2 import SessionConfigEditor


if platform.system() == "Windows":
    pg.setConfigOptions(useOpenGL=True)

log = logging.getLogger(__name__)

DEGREE_SYMBOL = "\u00b0"
LEGEND_LABEL_FORMAT = "Subsweep {ss_idx}, Channel #{ch_nbr} (Tx{tx_idx}, Rx{rx_idx})"


@attrs.mutable
class SharedState:
    session_config: a2.SessionConfig
    metadata: t.Optional[Metadata]

    def _collect_validation_results(self) -> list[ValidationResult]:
        return self.session_config._collect_validation_results()


class BackendPlugin(A2BackendPluginBase[SharedState]):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        super().__init__(*args, **kwargs)
        self.shared_state = SharedState(a2.SessionConfig.default(), None)
        self.steering_vector_cache: dict[tuple[int, int], npt.NDArray[np.complex128]] = {}
        self.broadcast()

    def _start_session(self, recorder: t.Optional[a2.H5Recorder]) -> None:
        assert self.client is not None

        if recorder:
            self.client.attach_recorder(recorder)

        self.shared_state.metadata = self.client.setup_session(self.shared_state.session_config)

        self.client.start_session()
        self.broadcast()

    def get_next(self) -> None:
        assert self.client is not None

        group_result = self.client.get_next(format=a2.Client.ResultFormat.FULL)

        self.callback(backend.PlotMessage(result=(group_result, None)))

    def end_session(self) -> None:
        assert self.client is not None

        self.client.stop_session()

        recorder = self.client.detach_recorder()
        if recorder is not None:
            recorder.close()

    @is_task
    def update_session_config(self, session_config: a2.SessionConfig) -> None:
        self.shared_state.session_config = session_config
        self.broadcast()

    @is_task
    def set_preset(self, preset_id: int) -> None:
        if preset_id == PluginPresetId.DEFAULT.value:
            self.update_session_config(a2.SessionConfig.default())
            self.broadcast()
        else:
            msg = f"Unknown preset id {preset_id}"
            raise RuntimeError(msg)

    def load_from_record_setup(
        self,
        *,
        record: a2.H5Record,
        config_override: t.Optional[t.Any] = None,
        context_override: t.Optional[t.Any] = None,
    ) -> None:
        if config_override is not None:
            self._logger.warning(f"Ignoring config override of type: {type(config_override)}")
        if context_override is not None:
            self._logger.warning(f"Ignoring context override of type: {type(context_override)}")

        self.update_session_config(record.session_config)

    def _load_from_cache(self, file: h5py.File) -> SharedState:
        cached: dict[str, t.Any] = {}
        if dataset := file.get("session_config"):
            cached["session_config"] = a2.SessionConfig.from_json(bytes.decode(dataset[()]))

        return attrs.evolve(self.shared_state, **cached)

    def save_to_cache(self, file: h5py.File) -> None:
        file.create_dataset("session_config", data=self.shared_state.session_config.to_json())


class ViewPlugin(A2ViewPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)

        self.start_button = QPushButton(icons.PLAY(), "Start measurement")
        self.start_button.setShortcut("space")
        self.start_button.setToolTip("Starts the session.\n\nShortcut: Space")
        self.start_button.clicked.connect(self._send_start_request)

        self.stop_button = QPushButton(icons.STOP(), "Stop")
        self.stop_button.setShortcut("space")
        self.stop_button.setToolTip("Stops the session.\n\nShortcut: Space")
        self.stop_button.clicked.connect(self._send_stop_request)

        self.misc_error_view = MiscErrorView(self)
        self.session_config_editor = SessionConfigEditor()
        self.session_config_editor.set_data(a2.SessionConfig.default())
        self.session_config_editor.sig_update.connect(self._update_session_config)

        button_group = GroupBox.grid("Controls")
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.invalid_config_note, 1, 0, 1, 2)

        sticky_layout = QVBoxLayout()
        sticky_layout.setContentsMargins(0, 0, 0, 0)
        sticky_layout.addWidget(button_group)
        self.sticky_widget.setLayout(sticky_layout)

        scrolly_layout = QVBoxLayout()
        scrolly_layout.setContentsMargins(0, 0, 0, 0)
        scrolly_layout.addWidget(self.misc_error_view)
        scrolly_layout.addWidget(self.session_config_editor)
        self.scrolly_widget.setLayout(scrolly_layout)

        goto_resource_button = GotoResourceTabButton()
        goto_resource_button.clicked.connect(
            lambda: app_model.sig_resource_tab_input_block_requested.emit(
                self.session_config_editor.get_data()
            )
        )
        scrolly_layout.insertWidget(0, goto_resource_button)

    def _update_session_config(self, session_config: a2.SessionConfig) -> None:
        BackendPlugin.update_session_config.rpc(
            self.app_model.put_task, session_config=session_config
        )

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(visual_policies.config_editor_enabled(app_model))
        self.stop_button.setEnabled(visual_policies.stop_button_enabled(app_model))

        no_gui_errors = self.session_config_editor.is_ready
        self.start_button.setEnabled(
            visual_policies.start_button_enabled(
                app_model, extra_condition=self._config_ready(no_gui_errors)
            )
        )

    def on_backend_state_update(self, state: t.Optional[SharedState]) -> None:
        if state is None:
            self.session_config_editor.set_data(None)
            self._update_config_validity([])
        else:
            self.session_config_editor.set_data(state.session_config)
            validation_results = state._collect_validation_results()
            self._update_config_validity(validation_results)
            not_handled = self.session_config_editor.handle_validation_results(validation_results)
            _ = self.misc_error_view.handle_validation_results(not_handled)


@attrs.frozen
class _PlotBlob:
    data: npt.NDArray[np.complex128]
    distances_m: npt.NDArray[np.float64]
    subsweep_index: int
    channel_index: int
    channel_number: int
    rx_index: int
    tx_index: int


class PlotPlugin(PlotPluginBase):
    def __init__(self, app_model: AppModel) -> None:
        super().__init__(app_model)
        self._plot_job: t.Optional[
            tuple[a2.GroupResult, dict[tuple[int, int], npt.NDArray[np.float64]]]
        ] = None
        self._config: t.Optional[a2.SessionConfig] = None

        self.tab_widget = TabPGWidget()

        self.envelope_phase_layout = self.tab_widget.newPlotWidget("Envelope && Phase")

        self.envelope_plot_item = self.envelope_phase_layout.addPlot(row=0, col=0)
        self.envelope_plot_item.getAxis("bottom").setLabel("Distance", units="m")
        self.envelope_plot_item.getAxis("left").setLabel("Amplitude")
        self.envelope_plot_item.showGrid(x=True, y=True, alpha=0.3)
        self.envelope_plot_smooth_max = et.utils.SmoothMax()

        self.phase_plot_item = self.envelope_phase_layout.addPlot(row=1, col=0)
        self.phase_plot_item.getAxis("bottom").setLabel("Distance", units="m")
        self.phase_plot_item.getAxis("left").setLabel("Phase")
        self.phase_plot_item.setYRange(-np.pi, np.pi)
        v_ticks = np.linspace(-1, 1, 5) * np.pi
        s_ticks = ["-\u03c0", "-\u03c0/2", "0", "\u03c0/2", "\u03c0"]
        self.phase_plot_item.getAxis("left").setTicks([[vs for vs in zip(v_ticks, s_ticks)]])
        self.phase_plot_item.showGrid(x=True, y=True, alpha=0.3)

        self.complex_layout = self.tab_widget.newPlotWidget("Complex")
        self.complex_plot_item = self.complex_layout.addPlot(row=0, col=0)
        self.complex_plot_item.getAxis("bottom").setLabel("I")
        self.complex_plot_item.getAxis("left").setLabel("Q")
        self.complex_smooth_max = et.utils.SmoothMax()

        layout = QVBoxLayout()
        layout.addWidget(self.tab_widget)
        self.setLayout(layout)

    def on_backend_state_update(self, state: t.Optional[SharedState]) -> None:
        if state is None:
            return

        self._config = state.session_config

        (min_range, max_range) = algo_utils.get_measured_range(self._config)

        self.envelope_plot_item.clear()
        self.envelope_plot_item.getAxis("bottom").setRange(min_range, max_range)
        self.envelope_plot_item.addLegend()

        self.phase_plot_item.clear()
        self.phase_plot_item.getAxis("bottom").setRange(min_range, max_range)
        self.phase_plot_item.addLegend()

        self.complex_plot_item.clear()
        self.complex_plot_item.addLegend()

    def handle_message(self, message: GeneralMessage) -> None:
        if isinstance(message, backend.PlotMessage):
            self._plot_job = message.result
        else:
            raise NotImplementedError

    def draw(self) -> None:
        if self._plot_job is None:
            return

        assert self._config is not None

        (group_result, _) = self._plot_job
        self._plot_job = None

        envelope_plot_fns = itertools.chain(
            (data_item.setData for data_item in self.envelope_plot_item.listDataItems()),
            itertools.repeat(self.envelope_plot_item.plot),
        )
        phase_plot_fns = itertools.chain(
            (data_item.setData for data_item in self.phase_plot_item.listDataItems()),
            itertools.repeat(self.phase_plot_item.plot),
        )

        for plot_blob, envelope_plot_fn, phase_plot_fn in zip(
            self._plot_blob_iter(group_result, self._config),
            envelope_plot_fns,
            phase_plot_fns,
        ):
            self._plot_envelope_data(plot_blob, plot_fn=envelope_plot_fn)
            self._plot_phase_data(plot_blob, plot_fn=phase_plot_fn)

        complex_plot_fns = itertools.chain(
            (data_item.setData for data_item in self.complex_plot_item.listDataItems()),
            itertools.repeat(self.complex_plot_item.plot),
        )

        for plot_blob, complex_plot_fn in zip(
            self._plot_blob_iter(group_result, self._config),
            complex_plot_fns,
        ):
            self._plot_complex_data(plot_blob, plot_fn=complex_plot_fn)

    @staticmethod
    def _plot_blob_iter(
        group_result: a2.GroupResult, config: a2.SessionConfig
    ) -> t.Iterator[_PlotBlob]:
        """Create a generator that yields PlotBlobs"""
        for result, sensor_config in zip(group_result.results, config.sensor_configs):
            for subsweep_idx, subsweep_config in enumerate(sensor_config.subsweeps):
                ch_nbrs = ch_conv.get_tx_major_channel_numbers(
                    subsweep_config.tx_antenna_mask,
                    subsweep_config.rx_antenna_mask,
                )

                for tx_major_ch_idx, (ch_nbr, (tx_idx, rx_idx)) in enumerate(ch_nbrs.items()):
                    data = result.get_subframe(
                        sensor_config, subsweep_idx, channel_indexes=[tx_major_ch_idx]
                    )
                    distances = algo_utils.get_distances_from_config(subsweep_config)
                    yield _PlotBlob(
                        data, distances, subsweep_idx, tx_major_ch_idx, ch_nbr, rx_idx, tx_idx
                    )

    def _plot_complex_data(self, plot_blob: _PlotBlob, plot_fn: t.Callable[..., t.Any]) -> None:
        if self.complex_layout.isHidden():
            return

        i = plot_blob.data.real.flatten()
        q = plot_blob.data.imag.flatten()

        plot_fn(
            i,
            q,
            pen=None,
            symbol="o",
            symbolBrush=et.utils.pg_brush_cycler(plot_blob.channel_index),
            name=LEGEND_LABEL_FORMAT.format(
                ss_idx=plot_blob.subsweep_index,
                ch_nbr=plot_blob.channel_number,
                tx_idx=plot_blob.tx_index,
                rx_idx=plot_blob.rx_index,
            ),
        )

        lim = self.complex_smooth_max.update(np.max([np.max(np.abs(i)), np.max(np.abs(q))])) * 1.05
        self.complex_plot_item.setYRange(-lim, lim)
        self.complex_plot_item.setXRange(-lim, lim)

    def _plot_envelope_data(self, plot_blob: _PlotBlob, plot_fn: t.Callable[..., t.Any]) -> None:
        if self.envelope_phase_layout.isHidden():
            return

        styles = [
            Qt.PenStyle.SolidLine,
            Qt.PenStyle.DashLine,
            Qt.PenStyle.DotLine,
            Qt.PenStyle.DashDotLine,
            Qt.PenStyle.DashDotDotLine,
        ]
        style = styles[plot_blob.subsweep_index % len(styles)]

        envelope = algo_utils.get_frame_envelope(plot_blob.data)

        plot_fn(
            plot_blob.distances_m,
            envelope,
            pen=et.utils.pg_pen_cycler(plot_blob.channel_index, style=style),
            name=LEGEND_LABEL_FORMAT.format(
                ss_idx=plot_blob.subsweep_index,
                ch_nbr=plot_blob.channel_number,
                tx_idx=plot_blob.tx_index,
                rx_idx=plot_blob.rx_index,
            ),
        )

        lim = self.envelope_plot_smooth_max.update(np.max(envelope))
        self.envelope_plot_item.setYRange(0, lim * 1.05)

    def _plot_phase_data(self, plot_blob: _PlotBlob, plot_fn: t.Callable[..., t.Any]) -> None:
        if self.envelope_phase_layout.isHidden():
            return

        symbols = ["o", "s", "t", "d", "+", "t1", "t2", "t2", "p", "h", "star", "x"]
        symbol = symbols[plot_blob.subsweep_index % len(symbols)]

        phase = algo_utils.get_frame_phase(plot_blob.data, degrees=False)

        plot_fn(
            plot_blob.distances_m,
            phase,
            pen=None,
            symbol=symbol,
            symbolBrush=et.utils.pg_brush_cycler(plot_blob.channel_index),
            name=LEGEND_LABEL_FORMAT.format(
                ss_idx=plot_blob.subsweep_index,
                ch_nbr=plot_blob.channel_number,
                tx_idx=plot_blob.tx_index,
                rx_idx=plot_blob.rx_index,
            ),
        )
