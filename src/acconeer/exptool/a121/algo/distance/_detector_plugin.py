# Copyright (c) Acconeer AB, 2022
# All rights reserved

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Any, Callable, Optional

import attrs
import numpy as np
import qtawesome as qta

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

import pyqtgraph as pg

import acconeer.exptool as et
from acconeer.exptool import a121
from acconeer.exptool.a121.algo._plugins import (
    DetectorBackendPluginBase,
    DetectorPlotPluginBase,
    DetectorViewPluginBase,
)
from acconeer.exptool.app.new import (
    BUTTON_ICON_COLOR,
    AppModel,
    ConnectionState,
    GeneralMessage,
    HandledException,
    Message,
    Plugin,
    PluginFamily,
    PluginGeneration,
    PluginState,
    PluginStateMessage,
    get_temp_h5_path,
    is_task,
)
from acconeer.exptool.app.new.ui.plugin import (
    AttrsConfigEditor,
    GridGroupBox,
    PidgetFactoryMapping,
    pidgets,
    utils,
)

from ._detector import (
    DetailedStatus,
    Detector,
    DetectorConfig,
    DetectorContext,
    DetectorResult,
    PeakSortingMethod,
    ThresholdMethod,
    _load_algo_data,
)


log = logging.getLogger(__name__)


@attrs.mutable(kw_only=True)
class SharedState:
    sensor_id: int = attrs.field(default=1)
    config: DetectorConfig = attrs.field(factory=DetectorConfig)
    context: DetectorContext = attrs.field(factory=DetectorContext)
    replaying: bool = attrs.field(default=False)


@attrs.frozen(kw_only=True)
class Save:
    config: DetectorConfig = attrs.field()
    context: DetectorContext = attrs.field()


def serialized_attrs_instance_has_diverged(attrs_instance: Any) -> bool:
    """Checks (recursively) if a de-serialized attrs-instances contains
    all attributes defined its respective class definition.

    :param attrs_config:
        An instance of an attrs-class, that possibly contains other attrs-instances.
    :returns: True if any attrs-instance have diverged from its class, False otherwise
    """
    # TODO: Should end up in the `Config` ABC
    attrs_class = type(attrs_instance)
    if not attrs.has(attrs_class):
        raise TypeError(f"Cannot check object of type {attrs_class!r}. It's not an attrs-class.")

    for attribute in attrs_instance.__attrs_attrs__:
        try:
            value = getattr(attrs_instance, attribute.name)

            if attrs.has(type(value)) and serialized_attrs_instance_has_diverged(value):
                return True
        except AttributeError:
            log.info(
                f"Serialized object of type {attrs_class.__name__!r} "
                + "seems to have converged from its definition."
            )
            log.info(f"Should contain the attribute {attribute.name!r} but did not.")
            return True

    return False


class BackendPlugin(DetectorBackendPluginBase[SharedState]):
    def __init__(self, callback: Callable[[Message], None], key: str) -> None:
        super().__init__(callback=callback, key=key)

        self._started: bool = False
        self._live_client: Optional[a121.Client] = None
        self._replaying_client: Optional[a121._ReplayingClient] = None
        self._recorder: Optional[a121.H5Recorder] = None
        self._opened_record: Optional[a121.H5Record] = None
        self._detector_instance: Optional[Detector] = None

        self.restore_defaults()

    @is_task
    def deserialize(self, *, data: bytes) -> None:
        try:
            obj = pickle.loads(data)
        except Exception:
            log.warning("Could not load pickled - pickle.loads() failed")
            return

        if not isinstance(obj, Save):
            log.warning("Could not load pickled - not the correct type")
            return

        type_matches = [
            isinstance(obj.config, DetectorConfig),
            isinstance(obj.context, DetectorContext),
        ]
        if not all(type_matches):
            log.warning("Could not load pickled - not the correct type")
            return

        if serialized_attrs_instance_has_diverged(obj):
            log.warning("Could not load pickled - cached config is uncompatible.")
            return

        self.shared_state.config = obj.config
        self.shared_state.context = obj.context

        self.broadcast(sync=True)

    def _serialize(self) -> bytes:
        obj = Save(
            config=self.shared_state.config,
            context=self.shared_state.context,
        )
        return pickle.dumps(obj, protocol=4)

    def broadcast(self, sync: bool = False) -> None:
        super().broadcast()

        if sync:
            self.callback(GeneralMessage(name="sync", recipient="view_plugin"))

    @is_task
    def restore_defaults(self) -> None:
        self.shared_state = SharedState()
        self.broadcast(sync=True)

    @property
    def _client(self) -> Optional[a121.Client]:
        if self._replaying_client is not None:
            return self._replaying_client

        return self._live_client

    def idle(self) -> bool:
        if self._started:
            self._get_next()
            return True
        else:
            return False

    def attach_client(self, *, client: Any) -> None:
        self._live_client = client

    def detach_client(self) -> None:
        self._live_client = None

    @is_task
    def update_config(self, *, config: DetectorConfig) -> None:
        self.shared_state.config = config
        self.broadcast()

    @is_task
    def update_sensor_id(self, *, sensor_id: int) -> None:
        self.shared_state.sensor_id = sensor_id
        self.broadcast()

    def teardown(self) -> None:
        self.callback(
            GeneralMessage(
                name="serialized",
                kwargs={
                    "generation": PluginGeneration.A121,
                    "key": self.key,
                    "data": self._serialize(),
                },
            )
        )
        self.detach_client()

    @is_task
    def load_from_file(self, *, path: Path) -> None:
        try:
            self._load_from_file_setup(path=path)
        except Exception as exc:
            self._opened_record = None
            self._replaying_client = None
            self.shared_state.replaying = False

            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not load from file") from exc

        self.shared_state.replaying = True

        self.start_session(with_recorder=False)

        self.send_status_message(f"<b>Replaying from {path.name}</b>")
        self.broadcast(sync=True)

    def _load_from_file_setup(self, *, path: Path) -> None:
        r = a121.open_record(path)
        assert isinstance(r, a121.H5Record)
        self._opened_record = r
        self._replaying_client = a121._ReplayingClient(self._opened_record)

        algo_group = self._opened_record.get_algo_group(self.key)
        _, config, context = _load_algo_data(algo_group)
        self.shared_state.config = config
        self.shared_state.context = context

    @is_task
    def start_session(self, *, with_recorder: bool = True) -> None:
        if self._started:
            raise RuntimeError

        if self._client is None:
            raise RuntimeError

        if not self._client.connected:
            raise RuntimeError

        self._detector_instance = Detector(
            client=self._client,
            sensor_id=self.shared_state.sensor_id,
            detector_config=self.shared_state.config,
            context=self.shared_state.context,
        )

        if with_recorder:
            self._recorder = a121.H5Recorder(get_temp_h5_path())
        else:
            self._recorder = None

        try:
            self._detector_instance.start(
                self._recorder, skip_calibration=self.shared_state.replaying
            )
        except Exception as exc:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            raise HandledException("Could not start") from exc

        self._started = True

        self.broadcast()

        self.callback(
            GeneralMessage(
                name="setup",
                kwargs=dict(num_curves=len(self._detector_instance.processor_specs)),
                recipient="plot_plugin",
            )
        )
        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

    @is_task
    def stop_session(self) -> None:
        if not self._started:
            raise RuntimeError

        if self._detector_instance is None:
            raise RuntimeError

        try:
            self._detector_instance.stop()
        except Exception as exc:
            raise HandledException("Failure when stopping session") from exc
        finally:
            if self._recorder is not None:
                assert self._recorder.path is not None
                path = Path(self._recorder.path)
                self.callback(GeneralMessage(name="saveable_file", data=path))
                self._recorder = None

            if self.shared_state.replaying:
                assert self._opened_record is not None
                self._opened_record.close()

                self._opened_record = None
                self._replaying_client = None

                self.shared_state.replaying = False

            self._started = False
            self.broadcast()
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))
            self.callback(GeneralMessage(name="result_tick_time", data=None))

    def _get_next(self) -> None:
        if not self._started:
            raise RuntimeError

        if self._detector_instance is None:
            raise RuntimeError

        try:
            result = self._detector_instance.get_next()
        except a121._StopReplay:
            self.stop_session()
            return
        except Exception as exc:
            try:
                self.stop_session()
            except Exception:
                pass

            raise HandledException("Failed to get_next") from exc

        _, _, some_service_result = next(
            a121.iterate_extended_structure(result.service_extended_result)
        )
        self.callback(GeneralMessage(name="result_tick_time", data=some_service_result.tick_time))

        self.callback(GeneralMessage(name="plot", data=result, recipient="plot_plugin"))

    @is_task
    def record_threshold(self) -> None:
        if self._started:
            raise RuntimeError

        if self._client is None:
            raise RuntimeError

        if not self._client.connected:
            raise RuntimeError

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

        try:
            self._detector_instance = Detector(
                client=self._client,
                sensor_id=self.shared_state.sensor_id,
                detector_config=self.shared_state.config,
                context=self.shared_state.context,
            )
            self._detector_instance.record_threshold()
        except Exception as exc:
            raise HandledException("Failed to record threshold") from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context
        self.broadcast()

    @is_task
    def calibrate_close_range(self) -> None:
        if self._started:
            raise RuntimeError

        if self._client is None:
            raise RuntimeError

        if not self._client.connected:
            raise RuntimeError

        self.callback(PluginStateMessage(state=PluginState.LOADED_BUSY))

        try:
            self._detector_instance = Detector(
                client=self._client,
                sensor_id=self.shared_state.sensor_id,
                detector_config=self.shared_state.config,
                context=self.shared_state.context,
            )
            self._detector_instance.calibrate_close_range()
        except Exception as exc:
            raise HandledException("Failed to calibrate close range") from exc
        finally:
            self.callback(PluginStateMessage(state=PluginState.LOADED_IDLE))

        self.shared_state.context = self._detector_instance.context
        self.broadcast()


class PlotPlugin(DetectorPlotPluginBase):
    def __init__(self, *, plot_layout: pg.GraphicsLayout, app_model: AppModel) -> None:
        super().__init__(plot_layout=plot_layout, app_model=app_model)

    def setup_from_message(self, message: GeneralMessage) -> None:
        assert message.kwargs is not None
        self.setup(**message.kwargs)

    def update_from_message(self, message: GeneralMessage) -> None:
        self.update(message.data)  # type: ignore[arg-type]

    def setup(self, num_curves: int) -> None:
        self.num_curves = num_curves
        self.distance_history = [np.NaN] * 100

        win = self.plot_layout

        self.sweep_plot = win.addPlot(row=0, col=0)
        self.sweep_plot.setMenuEnabled(False)
        self.sweep_plot.showGrid(x=True, y=True)
        self.sweep_plot.addLegend()
        self.sweep_plot.setLabel("left", "Amplitude")
        self.sweep_plot.setLabel("bottom", "Distance (m)")
        self.sweep_plot.addItem(pg.PlotDataItem())

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.sweep_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        pen = et.utils.pg_pen_cycler(1)
        brush = et.utils.pg_brush_cycler(1)
        symbol_kw = dict(symbol="o", symbolSize=1, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.threshold_curves = [self.sweep_plot.plot(**feat_kw) for _ in range(self.num_curves)]

        sweep_plot_legend = pg.LegendItem(offset=(0.0, 0.5))
        sweep_plot_legend.setParentItem(self.sweep_plot)
        sweep_plot_legend.addItem(self.sweep_curves[0], "Sweep")
        sweep_plot_legend.addItem(self.threshold_curves[0], "Threshold")

        self.dist_history_plot = win.addPlot(row=1, col=0)
        self.dist_history_plot.setMenuEnabled(False)
        self.dist_history_plot.showGrid(x=True, y=True)
        self.dist_history_plot.addLegend()
        self.dist_history_plot.setLabel("left", "Estimated distance (m)")
        self.dist_history_plot.addItem(pg.PlotDataItem())
        self.dist_history_plot.setXRange(0, len(self.distance_history))

        pen = et.utils.pg_pen_cycler(0)
        brush = et.utils.pg_brush_cycler(0)
        symbol_kw = dict(symbol="o", symbolSize=5, symbolBrush=brush, symbolPen="k")
        feat_kw = dict(pen=pen, **symbol_kw)
        self.dist_history_curve = self.dist_history_plot.plot(**feat_kw)

        self.sweep_smooth_max = et.utils.SmoothMax()
        self.distance_hist_smooth_lim = et.utils.SmoothLimits()

    def update(self, result: DetectorResult) -> None:
        assert result.distances is not None

        self.distance_history.pop(0)
        self.distance_history.append(result.distances[0])

        max_val_in_plot = 0
        for idx, processor_result in enumerate(result.processor_results):
            assert processor_result.extra_result.used_threshold is not None
            assert processor_result.extra_result.distances_m is not None
            assert processor_result.extra_result.abs_sweep is not None

            abs_sweep = processor_result.extra_result.abs_sweep
            threshold = processor_result.extra_result.used_threshold
            distances_m = processor_result.extra_result.distances_m

            self.sweep_curves[idx].setData(distances_m, abs_sweep)
            self.threshold_curves[idx].setData(distances_m, threshold)

            max_val_in_subsweep = max(max(threshold), max(abs_sweep))
            if max_val_in_plot < max_val_in_subsweep:
                max_val_in_plot = max_val_in_subsweep

        self.sweep_plot.setYRange(0, self.sweep_smooth_max.update(max_val_in_plot))

        if np.any(~np.isnan(self.distance_history)):
            self.dist_history_curve.setData(self.distance_history)
            lims = self.distance_hist_smooth_lim.update(self.distance_history)
            self.dist_history_plot.setYRange(lims[0], lims[1])
        else:
            self.dist_history_curve.setData([])


class ViewPlugin(DetectorViewPluginBase):

    TEXT_MSG_MAP = {
        DetailedStatus.OK: "Ready to start.",
        DetailedStatus.CLOSE_RANGE_CALIBRATION_MISSING: "Run close range calibration.",
        DetailedStatus.CLOSE_RANGE_CALIBRATION_CONFIG_MISMATCH: (
            "Configuration does not match"
            + " configuration used during close range calibration. Please rerun calibration."
        ),
        DetailedStatus.RECORDED_THRESHOLD_MISSING: "Run recorded threshold calibration.",
        DetailedStatus.RECORDED_THRESHOLD_CONFIG_MISMATCH: (
            "Configuration does not match configuration"
            + " used during recorded threshold calibration. Please rerun calibration."
        ),
        DetailedStatus.INVALID_DETECTOR_CONFIG_RANGE: (
            "Invalid detector config. Valid measurement"
            + " range is "
            + str(Detector.MIN_DIST_M)
            + "-"
            + str(Detector.MAX_DIST_M)
            + "m."
        ),
    }

    def __init__(self, app_model: AppModel, view_widget: QWidget) -> None:
        super().__init__(app_model=app_model, view_widget=view_widget)

        self.view_layout = QVBoxLayout(self.view_widget)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_widget.setLayout(self.view_layout)

        # TODO: Fix parents

        self.start_button = QPushButton(
            qta.icon("fa5s.play-circle", color=BUTTON_ICON_COLOR),
            "Start measurement",
            self.view_widget,
        )
        self.start_button.setShortcut("space")
        self.start_button.clicked.connect(self._send_start_request)

        self.stop_button = QPushButton(
            qta.icon("fa5s.stop-circle", color=BUTTON_ICON_COLOR),
            "Stop",
            self.view_widget,
        )
        self.stop_button.setShortcut("space")
        self.stop_button.clicked.connect(self._send_stop_request)

        self.record_threshold_button = QPushButton(
            qta.icon("fa.video-camera", color=BUTTON_ICON_COLOR),
            "Record threshold",
            self.view_widget,
        )
        self.record_threshold_button.clicked.connect(self._on_record_threshold)

        self.close_range_calibration_button = QPushButton(
            qta.icon("mdi.adjust", color=BUTTON_ICON_COLOR),
            "Calibrate close range",
            self.view_widget,
        )
        self.close_range_calibration_button.clicked.connect(self._on_close_range_calibration)

        self.defaults_button = QPushButton(
            qta.icon("mdi6.restore", color=BUTTON_ICON_COLOR),
            "Reset settings and calibrations",
            self.view_widget,
        )
        self.defaults_button.clicked.connect(self._send_defaults_request)

        self.message_box = QLabel(self.view_widget)
        self.message_box.setWordWrap(True)

        button_group = GridGroupBox("Controls", parent=self.view_widget)
        button_group.layout().addWidget(self.start_button, 0, 0)
        button_group.layout().addWidget(self.stop_button, 0, 1)
        button_group.layout().addWidget(self.close_range_calibration_button, 1, 0)
        button_group.layout().addWidget(self.record_threshold_button, 1, 1)
        button_group.layout().addWidget(self.defaults_button, 2, 0, 1, -1)
        button_group.layout().addWidget(self.message_box, 3, 0, 1, -1)
        self.view_layout.addWidget(button_group)

        sensor_selection_group = utils.VerticalGroupBox(
            "Sensor selection", parent=self.view_widget
        )
        self.sensor_id_pidget = pidgets.SensorIdParameterWidgetFactory(items=[]).create(
            parent=sensor_selection_group
        )
        self.sensor_id_pidget.sig_parameter_changed.connect(self._on_sensor_id_update)
        sensor_selection_group.layout().addWidget(self.sensor_id_pidget)
        self.view_layout.addWidget(sensor_selection_group)

        self.config_editor = AttrsConfigEditor[DetectorConfig](
            title="Detector parameters",
            factory_mapping=self._get_pidget_mapping(),
            parent=self.view_widget,
        )
        self.config_editor.sig_update.connect(self._on_config_update)
        self.view_layout.addWidget(self.config_editor)

        self.view_layout.addStretch(1)

    @classmethod
    def _get_pidget_mapping(cls) -> PidgetFactoryMapping:
        return {
            "start_m": pidgets.FloatParameterWidgetFactory(
                name_label_text="Range start",
                suffix=" m",
                decimals=3,
            ),
            "end_m": pidgets.FloatParameterWidgetFactory(
                name_label_text="Range end",
                suffix=" m",
                decimals=3,
            ),
            "max_step_length": pidgets.OptionalIntParameterWidgetFactory(
                name_label_text="Max step length",
                checkbox_label_text="Set",
                limits=(1, None),
                init_set_value=12,
            ),
            "max_profile": pidgets.EnumParameterWidgetFactory(
                name_label_text="Max profile",
                enum_type=a121.Profile,
                label_mapping={
                    a121.Profile.PROFILE_1: "1 (shortest)",
                    a121.Profile.PROFILE_2: "2",
                    a121.Profile.PROFILE_3: "3",
                    a121.Profile.PROFILE_4: "4",
                    a121.Profile.PROFILE_5: "5 (longest)",
                },
            ),
            "num_frames_in_recorded_threshold": pidgets.IntParameterWidgetFactory(
                name_label_text="Num frames in rec. thr.",
                limits=(1, None),
            ),
            "threshold_method": pidgets.EnumParameterWidgetFactory(
                name_label_text="Threshold method",
                enum_type=ThresholdMethod,
                label_mapping={
                    ThresholdMethod.CFAR: "CFAR",
                    ThresholdMethod.FIXED: "Fixed",
                    ThresholdMethod.RECORDED: "Recorded",
                },
            ),
            "peaksorting_method": pidgets.EnumParameterWidgetFactory(
                name_label_text="Peak sorting method",
                enum_type=PeakSortingMethod,
                label_mapping={
                    PeakSortingMethod.STRONGEST: "Strongest",
                    PeakSortingMethod.CLOSEST: "Closest",
                    PeakSortingMethod.HIGHEST_RCS: "Highest RCS",
                },
            ),
            "fixed_threshold_value": pidgets.FloatParameterWidgetFactory(
                name_label_text="Fixed threshold value",
                decimals=1,
                limits=(0, None),
            ),
            "threshold_sensitivity": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Threshold sensitivity",
                decimals=2,
                limits=(0, 1),
                show_limit_values=False,
            ),
            "signal_quality": pidgets.FloatSliderParameterWidgetFactory(
                name_label_text="Signal quality",
                decimals=1,
                limits=(5, 25),
                show_limit_values=False,
                limit_texts=("Less power", "Higher quality"),
            ),
            "cfar_one_sided": pidgets.CheckboxParameterWidgetFactory(
                name_label_text="CFAR one sided",
            ),
        }

    def on_app_model_update(self, app_model: AppModel) -> None:
        state = app_model.backend_plugin_state
        self.sensor_id_pidget.update_available_sensor_list(app_model._a121_server_info)

        if state is None:
            self.start_button.setEnabled(False)
            self.close_range_calibration_button.setEnabled(False)
            self.record_threshold_button.setEnabled(False)
            self.stop_button.setEnabled(False)
            self.defaults_button.setEnabled(False)

            self.config_editor.set_data(None)
            self.config_editor.setEnabled(False)
            self.sensor_id_pidget.set_parameter(None)
            self.message_box.setText("")

            return

        assert isinstance(state, SharedState)

        self.defaults_button.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)

        self.config_editor.setEnabled(app_model.plugin_state == PluginState.LOADED_IDLE)
        self.config_editor.set_data(state.config)
        self.sensor_id_pidget.set_parameter(state.sensor_id)
        self.sensor_id_pidget.setEnabled(app_model.plugin_state.is_steady)

        detector_status = Detector.get_detector_status(state.config, state.context)

        self.message_box.setText(self.TEXT_MSG_MAP[detector_status.detector_state])

        ready_for_session = (
            app_model.plugin_state == PluginState.LOADED_IDLE
            and app_model.connection_state == ConnectionState.CONNECTED
        )

        self.close_range_calibration_button.setEnabled(
            ready_for_session and detector_status.ready_to_calibrate_close_range
        )
        self.record_threshold_button.setEnabled(
            ready_for_session and detector_status.ready_to_record_threshold
        )
        self.start_button.setEnabled(ready_for_session and detector_status.ready_to_start)
        self.stop_button.setEnabled(app_model.plugin_state == PluginState.LOADED_BUSY)

    def _on_sensor_id_update(self, sensor_id: int) -> None:
        self.app_model.put_backend_plugin_task("update_sensor_id", {"sensor_id": sensor_id})

    # TODO: move to detector base (?)
    def _on_config_update(self, config: DetectorConfig) -> None:
        self.app_model.put_backend_plugin_task("update_config", {"config": config})

    # TODO: move to detector base (?)
    def handle_message(self, message: GeneralMessage) -> None:
        if message.name == "sync":
            log.debug(f"{type(self).__name__} syncing")

            self.config_editor.sync()
        else:
            raise RuntimeError("Unknown message")

    # TODO: move to detector base (?)
    def _send_start_request(self) -> None:
        self.app_model.put_backend_plugin_task("start_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    # TODO: move to detector base (?)
    def _send_stop_request(self) -> None:
        self.app_model.put_backend_plugin_task("stop_session", on_error=self.app_model.emit_error)
        self.app_model.set_plugin_state(PluginState.LOADED_STOPPING)

    def _on_record_threshold(self) -> None:
        self.app_model.put_backend_plugin_task("record_threshold")
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _on_close_range_calibration(self) -> None:
        self.app_model.put_backend_plugin_task("calibrate_close_range")
        self.app_model.set_plugin_state(PluginState.LOADED_STARTING)

    def _send_defaults_request(self) -> None:
        self.app_model.put_backend_plugin_task("restore_defaults")

    # TODO: move to detector base (?)
    def teardown(self) -> None:
        self.view_layout.deleteLater()


DISTANCE_DETECTOR_PLUGIN = Plugin(
    generation=PluginGeneration.A121,
    key="distance_detector",
    title="Distance detector",
    description="Easily measure distance to objects.",
    family=PluginFamily.DETECTOR,
    backend_plugin=BackendPlugin,
    plot_plugin=PlotPlugin,
    view_plugin=ViewPlugin,
)
