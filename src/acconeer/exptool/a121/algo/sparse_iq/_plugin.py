from __future__ import annotations

import logging
from typing import Callable, Optional, Tuple

import numpy as np
import numpy.typing as npt

from PySide6.QtGui import QTransform
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121 import algo
from acconeer.exptool.a121.algo._plugins import (
    ProcessorBackendPluginBase,
    ProcessorPlotPluginBase,
    ProcessorViewPluginBase,
)
from acconeer.exptool.app.new import (
    AppModel,
    BusyMessage,
    ConnectionState,
    DataMessage,
    IdleMessage,
    KwargMessage,
    Message,
    OkMessage,
    Plugin,
    PluginFamily,
    PluginGeneration,
    PluginState,
    Task,
)
from acconeer.exptool.app.new.ui.plugin import AttrsConfigEditor, SessionConfigEditor, pidgets

from ._processor import AmplitudeMethod, Processor, ProcessorConfig, ProcessorResult


log = logging.getLogger(__name__)


class BackendPlugin(ProcessorBackendPluginBase):
    _client: Optional[a121.Client]
    _processor_instance: Optional[Processor]

    def __init__(self, callback: Callable[[Message], None], key: str):
        super().__init__(callback=callback, key=key)
        self._processor_instance = None
        self._client = None
        self._send_default_configs_to_view()

    def _send_default_configs_to_view(self) -> None:
        self.callback(
            DataMessage(
                "session_config",
                a121.SessionConfig(),
                recipient="view_plugin",
            )
        )
        self.callback(
            DataMessage(
                "processor_config",
                ProcessorConfig(),
                recipient="view_plugin",
            )
        )

    def attach_client(self, *, client: a121.Client) -> None:
        self._client = client

    def detach_client(self) -> None:
        self._client = None

    def teardown(self) -> None:
        self.detach_client()

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
            try:
                self._execute_start(**task_kwargs)
            except Exception as e:
                log.exception(e)
                self.callback(IdleMessage())
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
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'start'.")
        if not self._client.connected:
            # This check is here to avoid the
            # "auto-connect" behaviour in a121.Client.setup_session.
            raise RuntimeError("Client is not connected. Can not 'start'.")

        if session_config.extended:
            raise ValueError("Extended configs are not supported.")

        log.debug(f"SessionConfig has the update rate: {session_config.update_rate}")

        self.metadata = self._client.setup_session(session_config)
        assert isinstance(self.metadata, a121.Metadata)

        self._processor_instance = Processor(
            sensor_config=session_config.sensor_config,
            metadata=self.metadata,
            processor_config=processor_config,
        )
        self._client.start_session()
        self.callback(
            KwargMessage(
                "setup",
                dict(metadata=self.metadata, sensor_config=session_config.sensor_config),
                recipient="plot_plugin",
            )
        )
        self.callback(BusyMessage())

    def _execute_stop(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'stop'.")

        self._client.stop_session()
        self.callback(OkMessage("stop_session"))
        self.callback(IdleMessage())

    def _execute_get_next(self) -> None:
        if self._client is None:
            raise RuntimeError("Client is not attached. Can not 'get_next'.")
        if self._processor_instance is None:
            raise RuntimeError("Processor is None. 'start' needs to be called before 'get_next'")

        result = self._client.get_next()
        assert isinstance(result, a121.Result)

        processor_result = self._processor_instance.process(result)
        self.callback(DataMessage("plot", processor_result, recipient="plot_plugin"))


class ViewPlugin(ProcessorViewPluginBase):
    def __init__(self, view_widget: QWidget, app_model: AppModel) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)
        app_model.sig_message_view_plugin.connect(self._handle_addressed_message)
        self.view_widget = view_widget
        self.layout = QVBoxLayout(self.view_widget)
        self.view_widget.setLayout(self.layout)

        self.start_button = QPushButton("Start", self.view_widget)
        self.stop_button = QPushButton("Stop", self.view_widget)
        self.start_button.clicked.connect(self._send_start_requests)
        self.stop_button.clicked.connect(self._send_stop_requests)

        button_layout = QHBoxLayout(self.view_widget)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        self.layout.addLayout(button_layout)
        self.layout.addSpacing(10)

        self.session_config_editor = SessionConfigEditor(self.view_widget)
        self.processor_config_editor = AttrsConfigEditor[ProcessorConfig](
            title="Processor config parameters",
            pidget_mapping={
                "amplitude_method": (
                    pidgets.EnumParameterWidget(AmplitudeMethod, "Amplitude method:"),
                    id,
                )
            },
            parent=self.view_widget,
        )
        self.layout.addWidget(self.processor_config_editor)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.session_config_editor)
        self.layout.addStretch()

    def _send_start_requests(self) -> None:
        self.send_backend_task(
            (
                "start_session",
                {
                    "session_config": self.session_config_editor.session_config,
                    "processor_config": self.processor_config_editor.config,
                },
            )
        )
        self.send_backend_command(("set_idle_task", ("get_next", {})))
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_stop_requests(self) -> None:
        self.send_backend_command(("set_idle_task", None))
        self.send_backend_task(("stop_session", {}))
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def teardown(self) -> None:
        self.layout.deleteLater()

    def _handle_addressed_message(self, message: Message) -> None:
        if message.command_name == "session_config":
            self.session_config_editor.session_config = message.data
        elif message.command_name == "processor_config":
            self.processor_config_editor.config = message.data
        else:
            raise ValueError(
                f"{self.__class__.__name__} cannot handle the message {message.command_name}"
            )

    def on_app_model_update(self, app_model: AppModel) -> None:
        self.session_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.processor_config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.start_button.setEnabled(
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def on_app_model_error(self, exception: Exception) -> None:
        pass  # TODO


class PlotPlugin(ProcessorPlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)
        app_model.sig_message_plot_plugin.connect(self.handle_message)
        self.smooth_max = et.utils.SmoothMax()
        self._is_setup = False
        self._plot_job = None

    def handle_message(self, message: Message) -> None:
        if message.command_name == "setup":
            assert isinstance(message, KwargMessage)
            self.setup(**message.kwargs)
        elif message.command_name == "plot":
            self._plot_job = message.data
        else:
            log.warn(
                f"{self.__class__.__name__} got an unsupported command: {message.command_name!r}."
            )

    def draw(self) -> None:
        if not self._is_setup or self._plot_job is None:
            return

        self._update_plot_data(self._plot_job)
        self._plot_job = None

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
        self._is_setup = True

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
        pen = et.utils.pg_pen_cycler(cycle_num)

        if len(depths_m) > 32:
            return pg.PlotDataItem(pen=pen)
        else:
            brush = et.utils.pg_brush_cycler(cycle_num)
            return pg.PlotDataItem(
                pen=pen, symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k"
            )

    @staticmethod
    def _create_phase_curve(cycle_num: int) -> pg.PlotDataItem:
        brush = et.utils.pg_brush_cycler(cycle_num)
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
        phase_plot.getAxis("left").setTicks(et.utils.pg_phase_ticks)
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
        im.setLookupTable(et.utils.pg_mpl_cmap("viridis"))
        im.setTransform(transform)

        plot = parent.addPlot()
        plot.setMenuEnabled(False)
        plot.setLabel("bottom", "Distance (m)")
        plot.setLabel("left", "Velocity (m/s)")
        plot.addItem(im)

        return plot, im

    def on_app_model_update(self, app_model: AppModel) -> None:
        pass  # TODO

    def on_app_model_error(self, exception: Exception) -> None:
        pass  # TODO


SPARSE_IQ_PLUGIN = Plugin(
    generation=PluginGeneration.A121,
    key="sparse_iq",
    title="Sparse IQ",
    description="Basic usage of the sparse IQ service.",
    family=PluginFamily.SERVICE,
    backend_plugin=BackendPlugin,
    plot_plugin=PlotPlugin,
    view_plugin=ViewPlugin,
)
