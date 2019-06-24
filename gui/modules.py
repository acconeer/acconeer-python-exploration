from collections import namedtuple

from helper import PassthroughProcessor

import service_modules.envelope as envelope_module
import service_modules.iq as iq_module
import service_modules.sparse as sparse_module
import service_modules.power_bin as power_bin_module
import examples.processing.breathing as breathing_module
import examples.processing.phase_tracking as phase_tracking_module
import examples.processing.presence_detection_iq as presence_detection_iq_module
import examples.processing.presence_detection_sparse as presence_detection_sparse_module
import examples.processing.sleep_breathing as sleep_breathing_module
import examples.processing.obstacle_detection as obstacle_detection_module


ModuleInfo = namedtuple("ModuleInfo", [
    "label",
    "module",
    "sensor_config_class",
    "processor",
])

MODULE_INFOS = [
    ModuleInfo(
        "Select service",
        None,
        None,
        None,
    ),
    ModuleInfo(
        "IQ",
        iq_module,
        iq_module.get_sensor_config,
        iq_module.IQProcessor,
    ),
    ModuleInfo(
        "Envelope",
        envelope_module,
        envelope_module.get_sensor_config,
        envelope_module.EnvelopeProcessor,
    ),
    ModuleInfo(
        "Power bin",
        power_bin_module,
        power_bin_module.get_sensor_config,
        PassthroughProcessor,
    ),
    ModuleInfo(
        "Sparse",
        sparse_module,
        sparse_module.get_sensor_config,
        sparse_module.Processor,
    ),
    ModuleInfo(
        "Breathing",
        breathing_module,
        breathing_module.get_sensor_config,
        breathing_module.BreathingProcessor,
    ),
    ModuleInfo(
        "Phase tracking",
        phase_tracking_module,
        phase_tracking_module.get_sensor_config,
        phase_tracking_module.PhaseTrackingProcessor,
    ),
    ModuleInfo(
        "Presence detection (IQ)",
        presence_detection_iq_module,
        presence_detection_iq_module.get_sensor_config,
        presence_detection_iq_module.PresenceDetectionProcessor,
    ),
    ModuleInfo(
        "Presence detection (sparse)",
        presence_detection_sparse_module,
        presence_detection_sparse_module.get_sensor_config,
        presence_detection_sparse_module.PresenceDetectionSparseProcessor,
    ),
    ModuleInfo(
        "Sleep breathing",
        sleep_breathing_module,
        sleep_breathing_module.get_sensor_config,
        sleep_breathing_module.PresenceDetectionProcessor,
    ),
    ModuleInfo(
        "Obstacle detection",
        obstacle_detection_module,
        obstacle_detection_module.get_sensor_config,
        obstacle_detection_module.ObstacleDetectionProcessor,
    ),
]

MODULE_LABEL_TO_MODULE_INFO_MAP = {mi.label: mi for mi in MODULE_INFOS}
