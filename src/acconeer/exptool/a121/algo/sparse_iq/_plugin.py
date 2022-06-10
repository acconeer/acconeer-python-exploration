from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

import numpy as np
import numpy.typing as npt

from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121 import algo
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorPlotPluginBase,
    ProcessorViewPluginBase,
)
from acconeer.exptool.app.new.backend import (
    Backend,
    DataMessage,
    KwargMessage,
    Message,
    OkMessage,
    Task,
)
from acconeer.exptool.app.new.plugin import Plugin, PluginFamily

from ._processor import Processor, ProcessorConfig, ProcessorResult


log = logging.getLogger(__name__)


class BackendPlugin(ProcessorBackendPluginBase):
    client: Optional[a121.Client]
    callback: Optional[Callable[[Message], None]]
    processor_instance: Optional[Processor]

    def __init__(self):
        self.processor_instance = None
        self.client = None
        self.callback = None

    def setup(self, *, callback: Callable[[Message], None]) -> None:
        self.callback = callback

    def attach_client(self, *, client: a121.Client) -> None:
        self.client = client

    def detach_client(self) -> None:
        self.client = None

    def teardown(self) -> None:
        self.detach_client()
        self.callback = None

    def execute_task(self, *, task: Task) -> None:
        """Accepts the following tasks:

        -   (
                "start_session",
                {
                    session_config=a121.SessionConfig
                    processor_config=ProcessorConfig
                }
            ) -> [a121.Metadata, a121.SensorConfig]
        - ("stop_session", <Ignored>) -> None
        - ("get_next", <Ignored>) -> ProcessorResult
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
        self,
        session_config: a121.SessionConfig,
        processor_config: ProcessorConfig,
    ) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if not self.client.connected:
            # This check is here to avoid the
            # "auto-connect" behaviour in a121.Client.setup_session.
            raise RuntimeError("Client is not connected. Can not 'start'.")

        if self.callback is None:
            raise RuntimeError("callback is None. 'setup' needs to be called before 'get_next'")
        if session_config.extended:
            raise ValueError("Extended configs are not supported.")

        self.metadata = self.client.setup_session(session_config)
        assert isinstance(self.metadata, a121.Metadata)

        self.processor_instance = Processor(
            sensor_config=session_config.sensor_config,
            metadata=self.metadata,
            processor_config=processor_config,
        )
        self.client.start_session()
        self.callback(
            KwargMessage(
                "setup", dict(metadata=self.metadata, sensor_config=session_config.sensor_config)
            )
        )

    def _execute_stop(self) -> None:
        if self.client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")
        if self.callback is None:
            raise RuntimeError("callback is None. 'setup' needs to be called before 'get_next'")

        self.client.stop_session()
        self.callback(OkMessage("stop_session"))

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
        self.callback(DataMessage("plot", processor_result))


class ViewPlugin(ProcessorViewPluginBase):
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
        self.backend.put_task(
            (
                "start_session",
                {
                    "session_config": a121.SessionConfig(),
                    "processor_config": ProcessorConfig(),
                },
            )
        )
        self.backend.set_idle_task(("get_next", {}))

    def _send_stop_requests(self) -> None:
        self.backend.clear_idle_task()
        self.backend.put_task(("stop_session", {}))

    def teardown(self) -> None:
        self.layout.deleteLater()


class PlotPlugin(ProcessorPlotPluginBase):
    def __init__(self, plot_widget: pg.GraphicsLayout) -> None:
        super().__init__(plot_widget)
        self.smooth_max = et.utils.SmoothMax()  # type: ignore[attr-defined]

    def handle_message(self, message: Message) -> None:
        if message.command_name == "setup":
            assert isinstance(message, KwargMessage)
            self.setup(**message.kwargs)
        elif message.command_name == "plot":
            self._update_plot_data(message.data)
        else:
            log.warn(
                f"{self.__class__.__name__} got an unsupported command: {message.command_name!r}."
            )

    def draw(self) -> None:
        ...

    def setup(self, metadata: a121.Metadata, sensor_config: a121.SensorConfig) -> None:
        if isinstance(metadata, list):
            raise ValueError("Support for extended configs is not implemented.")

        self.distances_m, _ = algo.get_distances_m(sensor_config, metadata)
        vels, vel_res = algo.get_approx_fft_vels(sensor_config)

        self.ampl_plot = self._create_amplitude_plot(self.plot_layout)
        self.ampl_curve = self._create_amplitude_curve(0, self.distances_m)
        self.ampl_plot.addDataItem(self.ampl_curve)

        self.plot_layout.nextRow()

        self.phase_plot = self._create_phase_plot(self.plot_layout)
        self.phase_curve = self._create_phase_curve(0)
        self.phase_plot.addDataItem(self.phase_curve)

        self.plot_layout.nextRow()

        self.ft_plot, self.ft_im = self._create_fft_plot(
            self.plot_layout,
            distances_m=self.distances_m,
            step_length_m=2.5e-3,
            vels=vels,
            vel_res=vel_res,
        )

    def _update_plot_data(self, processor_result: ProcessorResult) -> None:
        ampls = processor_result.amplitudes
        self.ampl_curve.setData(self.distances_m, ampls)
        self.phase_curve.setData(self.distances_m, processor_result.phases)
        self.ampl_plot.setYRange(0, self.smooth_max.update(ampls))
        dvm = processor_result.distance_velocity_map
        self.ft_im.updateImage(
            dvm.T,
            levels=(0, 1.05 * np.max(dvm)),
        )

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
        phase_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)  # type: ignore [attr-defined]
        return phase_plot

    @staticmethod
    def _create_fft_plot(
        parent: pg.GraphicsLayout,
        *,
        distances_m: npt.NDArray[np.float_],
        step_length_m: float,
        vels: npt.NDArray[np.float_],
        vel_res: float,
    ) -> Tuple[pg.PlotItem, pg.ImageItem]:
        transform = QTransform()
        transform.translate(distances_m[0], vels[0] - 0.5 * vel_res)
        transform.scale(step_length_m, vel_res)

        im = pg.ImageItem(autoDownsample=True)
        im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))  # type: ignore[attr-defined]
        im.setTransform(transform)

        plot = parent.addPlot()
        plot.setMenuEnabled(False)
        plot.setLabel("bottom", "Distance (m)")
        plot.setLabel("left", "Velocity (m/s)")
        plot.addItem(im)

        return plot, im


SPARSE_IQ_PLUGIN = Plugin(
    key="sparse_iq",
    title="Sparse IQ",
    description="Basic usage of the sparse IQ service.",
    family=PluginFamily.SERVICE,
    backend_plugin=BackendPlugin,
    plot_plugin=PlotPlugin,
    view_plugin=ViewPlugin,
)
