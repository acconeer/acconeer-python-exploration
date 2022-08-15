# Copyright (c) Acconeer AB, 2022
# All rights reserved


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        pass

    def process(self, data, data_info):
        return data


def multi_sensor_processor(processor_class):
    class CompositeProcessor:
        def __init__(self, sensor_config, processing_config, session_info, calibration=None):
            self.child_processors = []
            for _ in sensor_config.sensor:
                p = processor_class(sensor_config, processing_config, session_info)
                self.child_processors.append(p)

        def update_processing_config(self, processing_config):
            if hasattr(processor_class, "update_processing_config"):
                for p in self.child_processors:
                    p.update_processing_config(processing_config)

        def process(self, data, data_info):
            return [p.process(d, i) for p, d, i in zip(self.child_processors, data, data_info)]

    return CompositeProcessor


def multi_sensor_pg_updater(updater_class):
    class CompositePGUpdater:
        def __init__(self, sensor_config, processing_config, session_info):
            self.child_updaters = []
            for _ in sensor_config.sensor:
                u = updater_class(sensor_config, processing_config, session_info)
                self.child_updaters.append(u)

        def update_processing_config(self, processing_config):
            if hasattr(updater_class, "update_processing_config"):
                for u in self.child_updaters:
                    u.update_processing_config(processing_config)

        def setup(self, win):
            for i, u in enumerate(self.child_updaters):
                sublayout = win.addLayout(row=0, col=i)
                u.setup(sublayout)

        def update(self, data):
            for u, d in zip(self.child_updaters, data):
                u.update(d)

    return CompositePGUpdater
