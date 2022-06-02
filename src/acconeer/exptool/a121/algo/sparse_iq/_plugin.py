from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import numpy.typing as npt

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

import pyqtgraph as pg  # type: ignore[import]

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPlugin,
    ProcessorPlotPlugin,
    ProcessorViewPlugin,
)
from acconeer.exptool.a121.algo._utils import approx_distances_m, approx_fft_vels
from acconeer.exptool.app.new.backend import Backend
from acconeer.exptool.app.new.plugin import Plugin, Task

from ._processor import SparseIQProcessor, SparseIQProcessorConfig, SparseIQProcessorResult


class SparseIQProcessorBackendPlugin(ProcessorBackendPlugin):
    client: Optional[a121.Client]
    callback: Optional[Callable]
    processor_instance: Optional[SparseIQProcessor]

    def __init__(self):
        self.processor_instance = None
        self.client = None
        self.callback = None

    def setup(self, *, callback: Callable) -> None:
        self.callback = callback

    def attach_client(self, *, client: a121.Client) -> None:
        if not client.connected:
            raise RuntimeError("Only connected Clients can be attached.")
        self.client = client

    def detach_client(self) -> None:
        self.client = None

    def teardown(self) -> None:
        self.detach_client()
        self.callback = None

    def execute_task(self, *, task: Task) -> None:
        """Accepts the following tasks:

        - ("start_session", (a121.SessionConfig, SparseIQProcessorConfig)) -> None
        - ("stop_session", <Ignored>) -> None
        - ("get_next", <Ignored>) -> SparseIQProcessorResult
        """
        task_name, task_kwargs = task
        if task_name == "start_session":
            self._execute_start(**task_kwargs)
        elif task_name == "stop_session":
            self._execute_stop()
        elif task_name == "get_next":
            self._execute_get_next()
        else:
            raise RuntimeError(f"Unknown task: {task_name}")

    def _execute_start(
        self, session_config: a121.SessionConfig, processor_config: SparseIQProcessorConfig
    ) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if session_config.extended:
            raise RuntimeError("Extended configs are not supported.")

        metadata = self.client.setup_session(session_config)
        assert isinstance(metadata, a121.Metadata)

        self.processor_instance = SparseIQProcessor(
            sensor_config=session_config.sensor_config,
            metadata=metadata,
            processor_config=processor_config,
        )
        self.client.start_session()

    def _execute_stop(self) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")
        self.client.stop_session()

    def _execute_get_next(self) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'get_next'.")
        if self.processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")
        if self.callback is None:
            raise RuntimeError("callback is None. 'setup' needs to be called before 'get_next'")

        result = self.client.get_next()
        assert isinstance(result, a121.Result)

        processor_result = self.processor_instance.process(result)
        self.callback({"plot": processor_result, "get_next": processor_result})


class SparseIQProcessorViewPlugin(ProcessorViewPlugin):
    def __init__(self, *, parent: QWidget, backend: Backend) -> None:
        self.parent = parent
        self.backend = backend

    def setup(self) -> None:
        self.layout = QHBoxLayout()
        start_button = QPushButton("Start")
        stop_button = QPushButton("Stop")
        start_button.clicked.connect(self._send_start_requests)
        stop_button.clicked.connect(self._send_stop_requests)

        self.layout.addWidget(start_button)
        self.layout.addWidget(stop_button)
        self.parent.setLayout(self.layout)

    def _send_start_requests(self) -> None:
        # FIXME: don't hard-code these
        self.backend.put_task(("start_session", (a121.SessionConfig(), SparseIQProcessorConfig())))
        self.backend.set_idle_task("get_next")

    def _send_stop_requests(self) -> None:
        self.backend.clear_idle_task()
        self.backend.put_task(("stop_session", None))

    def teardown(self) -> None:
        self.layout.deleteLater()


class SparseIQProcessorPlotPlugin(ProcessorPlotPlugin):
    def __init__(self, sensor_config: a121.SensorConfig, *, parent: pg.GraphicsLayout) -> None:
        self.sensor_config = sensor_config
        self.parent = parent
        self.depths_m, self.step_length_m = approx_distances_m(sensor_config)
        self.vels, self.vel_res = approx_fft_vels(sensor_config)

    def setup(self) -> None:
        self.ampl_plot = self._create_amplitude_plot(self.parent)
        self.ampl_curve = self._create_amplitude_curve(0, self.depths_m)
        self.ampl_plot.addDataItem(self.ampl_curve)

        self.parent.nextRow()

        self.phase_plot = self._create_phase_plot(self.parent)
        self.phase_curve = self._create_phase_curve(0)
        self.phase_plot.addDataItem(self.phase_curve)

        self.parent.nextRow()

        self.ft_plot = self._create_fft_plot(self.parent)
        self.ft_im = pg.ImageItem(autoDownsample=True)
        self.ft_im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))  # type: ignore[attr-defined]
        self.ft_im.resetTransform()
        self.ft_plot.addItem(self.ft_im)
        self.smooth_max = et.utils.SmoothMax()  # type: ignore[attr-defined]

    @staticmethod
    def _create_amplitude_curve(
        cycle_num: int, depths_m: npt.NDArray[np.float_]
    ) -> pg.PlotDataItem:
        pen = et.utils.pg_pen_cycler(cycle_num)  # type: ignore[attr-defined]

        if len(depths_m) > 32:
            return pg.PlotDataItem(pen=pen)
        else:
            brush = et.utils.pg_brush_cycler(cycle_num)  # type: ignore[attr-defined]
            return pg.PlotDataItem(
                pen=pen, symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k"
            )

    @staticmethod
    def _create_phase_curve(cycle_num: int) -> pg.PlotDataItem:
        brush = et.utils.pg_brush_cycler(cycle_num)  # type: ignore[attr-defined]
        return pg.PlotDataItem(
            pen=None, symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k"
        )

    @staticmethod
    def _create_amplitude_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        ampl_plot = parent.addPlot()
        ampl_plot.setMenuEnabled(False)
        ampl_plot.showGrid(x=True, y=True)
        ampl_plot.setLabel("left", "Amplitude")
        return ampl_plot

    @staticmethod
    def _create_phase_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        phase_plot = parent.addPlot()
        phase_plot.setMenuEnabled(False)
        phase_plot.showGrid(x=True, y=True)
        phase_plot.setLabel("left", "Phase")
        phase_plot.setYRange(-np.pi, np.pi)
        # TODO:
        # phase_plot.getAxis("left").setTicks(utils.pg_phase_ticks)
        return phase_plot

    @staticmethod
    def _create_fft_plot(parent: pg.GraphicsLayout) -> pg.PlotItem:
        ft_plot = parent.addPlot()
        ft_plot.setMenuEnabled(False)
        ft_plot.setLabel("bottom", "Distance (m)")
        ft_plot.setLabel("left", "Velocity (m/s)")
        # TODO:
        # self.ft_im.translate(self.depths_m[0], self.vels[0] - 0.5 * self.vel_res)
        # self.ft_im.scale(self.step_length_m, self.vel_res)
        return ft_plot

    def update(self, processor_result: SparseIQProcessorResult) -> None:
        ampls = processor_result.amplitudes
        self.ampl_curve.setData(self.depths_m, ampls)
        self.phase_curve.setData(self.depths_m, processor_result.phases)
        self.ampl_plot.setYRange(0, self.smooth_max.update(ampls))
        abs_ft = processor_result.distance_velocity_map
        self.ft_im.updateImage(
            abs_ft.T,
            levels=(0, 1.05 * np.max(abs_ft[0])),
        )

    def teardown(self) -> None:
        self.parent.clear()


SPARSE_IQ_PLUGIN = Plugin(
    key="sparse_iq",
    backend_plugin=SparseIQProcessorBackendPlugin,
    plot_plugin=SparseIQProcessorPlotPlugin,
    view_plugin=SparseIQProcessorViewPlugin,
)
