from enum import Enum


class PluginFamily(Enum):
    SERVICE = "Services"
    DETECTOR = "Detectors"


class PluginGeneration(Enum):
    A111 = "a111"
    A121 = "a121"
