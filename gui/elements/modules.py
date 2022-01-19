from collections import namedtuple
from enum import Enum
from types import ModuleType

import acconeer.exptool.a111.algo.breathing as breathing_module
import acconeer.exptool.a111.algo.button_press as button_press_module
import acconeer.exptool.a111.algo.button_press_sparse as button_press_sparse_module
import acconeer.exptool.a111.algo.distance_detector as distance_detector_module
import acconeer.exptool.a111.algo.envelope as envelope_module
import acconeer.exptool.a111.algo.iq as iq_module
import acconeer.exptool.a111.algo.obstacle_detection as obstacle_detection_module
import acconeer.exptool.a111.algo.parking as parking_module
import acconeer.exptool.a111.algo.phase_tracking as phase_tracking_module
import acconeer.exptool.a111.algo.power_bins as power_bins_module
import acconeer.exptool.a111.algo.presence_detection_sparse as presence_detection_sparse_module  # noqa
import acconeer.exptool.a111.algo.sleep_breathing as sleep_breathing_module
import acconeer.exptool.a111.algo.sparse as sparse_module
import acconeer.exptool.a111.algo.sparse_fft as sparse_fft_module
import acconeer.exptool.a111.algo.sparse_inter_fft as sparse_inter_fft_module
import acconeer.exptool.a111.algo.sparse_speed as sparse_speed_module
from acconeer.exptool.modes import Mode

from .helper import PassthroughProcessor


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

        def process(self, data, data_info):
            return [p.process(d, i) for p, d, i in zip(self.processors, data, data_info)]

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


multi_sensor_distance_detector_module = multi_sensor_wrap(distance_detector_module)
multi_sensor_parking_module = multi_sensor_wrap(parking_module)
multi_sensor_sparse_speed_module = multi_sensor_wrap(sparse_speed_module)
multi_sensor_presence_detection_sparse_module = multi_sensor_wrap(presence_detection_sparse_module)

ModuleInfo = namedtuple(
    "ModuleInfo",
    [
        "key",
        "label",
        "module",
        "module_family",
        "sensor_config_class",
        "processor",
        "multi_sensor",
        "docs_url",
    ],
)


class ModuleFamily(Enum):
    EXAMPLE = "Example processing"
    SERVICE = "Services"
    DETECTOR = "Detectors"
    OTHER = None


MODULE_INFOS = [
    ModuleInfo(
        None,
        "Select service or detector",
        None,
        ModuleFamily.OTHER,
        None,
        None,
        True,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/services/index.html",
    ),
    ModuleInfo(
        Mode.ENVELOPE.name.lower(),
        "Envelope",
        envelope_module,
        ModuleFamily.SERVICE,
        envelope_module.get_sensor_config,
        envelope_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/services/envelope.html",
    ),
    ModuleInfo(
        Mode.IQ.name.lower(),
        "IQ",
        iq_module,
        ModuleFamily.SERVICE,
        iq_module.get_sensor_config,
        iq_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/services/iq.html",
    ),
    ModuleInfo(
        Mode.POWER_BINS.name.lower(),
        "Power bins",
        power_bins_module,
        ModuleFamily.SERVICE,
        power_bins_module.get_sensor_config,
        PassthroughProcessor,
        False,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/services/pb.html",
    ),
    ModuleInfo(
        Mode.SPARSE.name.lower(),
        "Sparse",
        sparse_module,
        ModuleFamily.SERVICE,
        sparse_module.get_sensor_config,
        sparse_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/services/sparse.html",
    ),
    ModuleInfo(
        "sparse_presence",
        "Presence detection (sparse)",
        multi_sensor_presence_detection_sparse_module,
        ModuleFamily.DETECTOR,
        multi_sensor_presence_detection_sparse_module.get_sensor_config,
        multi_sensor_presence_detection_sparse_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io"
        "/en/latest/processing/presence_detection_sparse.html",
    ),
    ModuleInfo(
        "sparse_fft",
        "Sparse short-time FFT (sparse)",
        sparse_fft_module,
        ModuleFamily.EXAMPLE,
        sparse_fft_module.get_sensor_config,
        sparse_fft_module.Processor,
        False,
        None,
    ),
    ModuleInfo(
        "sparse_inter_fft",
        "Sparse long-time FFT (sparse)",
        sparse_inter_fft_module,
        ModuleFamily.EXAMPLE,
        sparse_inter_fft_module.get_sensor_config,
        sparse_inter_fft_module.Processor,
        False,
        None,
    ),
    ModuleInfo(
        "sparse_speed",
        "Speed (sparse)",
        multi_sensor_sparse_speed_module,
        ModuleFamily.EXAMPLE,
        multi_sensor_sparse_speed_module.get_sensor_config,
        multi_sensor_sparse_speed_module.Processor,
        True,
        None,
    ),
    ModuleInfo(
        "iq_breathing",
        "Breathing (IQ)",
        breathing_module,
        ModuleFamily.EXAMPLE,
        breathing_module.get_sensor_config,
        breathing_module.BreathingProcessor,
        False,
        None,
    ),
    ModuleInfo(
        "iq_phase_tracking",
        "Phase tracking (IQ)",
        phase_tracking_module,
        ModuleFamily.EXAMPLE,
        phase_tracking_module.get_sensor_config,
        phase_tracking_module.PhaseTrackingProcessor,
        False,
        "https://acconeer-python-exploration.readthedocs.io"
        "/en/latest/processing/phase_tracking.html",
    ),
    ModuleInfo(
        "iq_sleep_breathing",
        "Sleep breathing (IQ)",
        sleep_breathing_module,
        ModuleFamily.EXAMPLE,
        sleep_breathing_module.get_sensor_config,
        sleep_breathing_module.Processor,
        False,
        "https://acconeer-python-exploration.readthedocs.io"
        "/en/latest/processing/sleep_breathing.html",
    ),
    ModuleInfo(
        "iq_obstacle",
        "Obstacle detection (IQ)",
        obstacle_detection_module,
        ModuleFamily.DETECTOR,
        obstacle_detection_module.get_sensor_config,
        obstacle_detection_module.ObstacleDetectionProcessor,
        [1, 2],
        "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/obstacle.html",
    ),
    ModuleInfo(
        "envelope_button_press",
        "Button Press (envelope)",
        button_press_module,
        ModuleFamily.EXAMPLE,
        button_press_module.get_sensor_config,
        button_press_module.ButtonPressProcessor,
        False,
        "https://acconeer-python-exploration.readthedocs.io/"
        "en/latest/processing/button_press.html",
    ),
    ModuleInfo(
        "button_press_sparse",
        "Button Press (sparse)",
        button_press_sparse_module,
        ModuleFamily.EXAMPLE,
        button_press_sparse_module.get_sensor_config,
        button_press_sparse_module.ButtonPressProcessor,
        False,
        None,
    ),
    ModuleInfo(
        "envelope_distance",
        "Distance Detector (envelope)",
        multi_sensor_distance_detector_module,
        ModuleFamily.DETECTOR,
        multi_sensor_distance_detector_module.get_sensor_config,
        multi_sensor_distance_detector_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io/"
        "en/latest/processing/distance_detector.html",
    ),
    ModuleInfo(
        "envelope_parking",
        "Parking (envelope)",
        multi_sensor_parking_module,
        ModuleFamily.DETECTOR,
        multi_sensor_parking_module.get_sensor_config,
        multi_sensor_parking_module.Processor,
        True,
        "https://acconeer-python-exploration.readthedocs.io/en/latest/processing/parking.html",
    ),
]

MODULE_KEY_TO_MODULE_INFO_MAP = {mi.key: mi for mi in MODULE_INFOS}
MODULE_LABEL_TO_MODULE_INFO_MAP = {mi.label: mi for mi in MODULE_INFOS}
