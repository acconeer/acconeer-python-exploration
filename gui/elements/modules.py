from collections import namedtuple
from types import ModuleType

from helper import PassthroughProcessor

import service_modules.envelope as envelope_module
import service_modules.iq as iq_module
import service_modules.sparse as sparse_module
import service_modules.power_bins as power_bins_module
import examples.processing.breathing as breathing_module
import examples.processing.phase_tracking as phase_tracking_module
import examples.processing.presence_detection_sparse as presence_detection_sparse_module
import examples.processing.sparse_fft as sparse_fft_module
import examples.processing.sparse_speed as sparse_speed_module
import examples.processing.sleep_breathing as sleep_breathing_module
import examples.processing.obstacle_detection as obstacle_detection_module
import examples.processing.button_press as button_press_module


def multi_sensor_wrap(module):
    processor_cls = module.__dict__["Processor"]

    class WrappedProcessor:
        def __init__(self, sensor_config, processing_config, session_info):
            self.processors = []
            for _ in sensor_config.sensor:
                p = processor_cls(sensor_config, processing_config, session_info)
                self.processors.append(p)

        def update_processing_config(self, processing_config):
            if hasattr(processor_cls, "update_processing_config"):
                for p in self.processors:
                    p.update_processing_config(processing_config)

        def process(self, data):
            return [p.process(d) for p, d in zip(self.processors, data)]

    updater_cls = module.__dict__["PGUpdater"]

    class WrappedPGUpdater:
        def __init__(self, sensor_config, processing_config, session_info):
            self.updaters = []
            for _ in sensor_config.sensor:
                u = updater_cls(sensor_config, processing_config, session_info)
                self.updaters.append(u)

        def update_processing_config(self, processing_config):
            if hasattr(updater_cls, "update_processing_config"):
                for u in self.updaters:
                    u.update_processing_config(processing_config)

        def setup(self, win):
            for i, u in enumerate(self.updaters):
                sublayout = win.addLayout(row=0, col=i)
                u.setup(sublayout)

        def update(self, data):
            for u, d in zip(self.updaters, data):
                u.update(d)

    obj = ModuleType("wrapped_" + module.__name__.split(".")[-1])
    obj.__dict__["Processor"] = WrappedProcessor
    obj.__dict__["PGUpdater"] = WrappedPGUpdater
    for k, v in module.__dict__.items():
        if k not in obj.__dict__:
            obj.__dict__[k] = v

    return obj


multi_sensor_sparse_speed_module = multi_sensor_wrap(sparse_speed_module)

ModuleInfo = namedtuple("ModuleInfo", [
    "label",
    "module",
    "sensor_config_class",
    "processor",
    "multi_sensor",
    "allow_ml"
])

MODULE_INFOS = [
    ModuleInfo(
        "Select service or detector",
        None,
        None,
        None,
        True,
        True,
    ),
    ModuleInfo(
        "IQ",
        iq_module,
        iq_module.get_sensor_config,
        iq_module.IQProcessor,
        True,
        True,
    ),
    ModuleInfo(
        "Envelope",
        envelope_module,
        envelope_module.get_sensor_config,
        envelope_module.Processor,
        True,
        True,
    ),
    ModuleInfo(
        "Power bins",
        power_bins_module,
        power_bins_module.get_sensor_config,
        PassthroughProcessor,
        False,
        False,
    ),
    ModuleInfo(
        "Sparse",
        sparse_module,
        sparse_module.get_sensor_config,
        sparse_module.Processor,
        True,
        True,
    ),
    ModuleInfo(
        "Presence detection (sparse)",
        presence_detection_sparse_module,
        presence_detection_sparse_module.get_sensor_config,
        presence_detection_sparse_module.PresenceDetectionSparseProcessor,
        False,
        False,
    ),
    ModuleInfo(
        "Sparse FFT (sparse)",
        sparse_fft_module,
        sparse_fft_module.get_sensor_config,
        sparse_fft_module.Processor,
        False,
        False,
    ),
    ModuleInfo(
        "Speed (sparse)",
        multi_sensor_sparse_speed_module,
        multi_sensor_sparse_speed_module.get_sensor_config,
        multi_sensor_sparse_speed_module.Processor,
        True,
        False,
    ),
    ModuleInfo(
        "Breathing (IQ)",
        breathing_module,
        breathing_module.get_sensor_config,
        breathing_module.BreathingProcessor,
        False,
        False,
    ),
    ModuleInfo(
        "Phase tracking (IQ)",
        phase_tracking_module,
        phase_tracking_module.get_sensor_config,
        phase_tracking_module.PhaseTrackingProcessor,
        False,
        False,
    ),
    ModuleInfo(
        "Sleep breathing (IQ)",
        sleep_breathing_module,
        sleep_breathing_module.get_sensor_config,
        sleep_breathing_module.PresenceDetectionProcessor,
        False,
        False,
    ),
    ModuleInfo(
        "Obstacle detection (IQ)",
        obstacle_detection_module,
        obstacle_detection_module.get_sensor_config,
        obstacle_detection_module.ObstacleDetectionProcessor,
        [1, 2],
        False,
    ),
    ModuleInfo(
        "Button Press (envelope)",
        button_press_module,
        button_press_module.get_sensor_config,
        button_press_module.ButtonPressProcessor,
        False,
        False,
    ),
]

MODULE_LABEL_TO_MODULE_INFO_MAP = {mi.label: mi for mi in MODULE_INFOS}
