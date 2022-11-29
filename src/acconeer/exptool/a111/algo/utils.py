# Copyright (c) Acconeer AB, 2022
# All rights reserved


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config, session_info, calibration=None):
        pass

    def process(self, data, data_info):
        return data


class CompositeProcessor:
    def __init__(
        self, sensor_config, processing_config, session_info, processor_class, calibration=None
    ):
        self.processor_class = processor_class
        self.child_processors = []
        for _ in sensor_config.sensor:
            p = self.processor_class(sensor_config, processing_config, session_info)
            self.child_processors.append(p)

    def update_processing_config(self, processing_config):
        if hasattr(self.processor_class, "update_processing_config"):
            for p in self.child_processors:
                p.update_processing_config(processing_config)

    def process(self, data, data_info):
        return [p.process(d, i) for p, d, i in zip(self.child_processors, data, data_info)]


class MultiSensorProcessorCreator:
    def __init__(self, processor_class):
        self.processor_class = processor_class

    def create_processor(self, sensor_config, processing_config, session_info, calibration=None):
        return CompositeProcessor(
            sensor_config, processing_config, session_info, self.processor_class, calibration
        )


class CompositePGUpdater:
    def __init__(self, sensor_config, processing_config, session_info, updater_class):
        self.updater_class = updater_class
        self.child_updaters = []
        for _ in sensor_config.sensor:
            u = self.updater_class(sensor_config, processing_config, session_info)
            self.child_updaters.append(u)

    def update_processing_config(self, processing_config):
        if hasattr(self.updater_class, "update_processing_config"):
            for u in self.child_updaters:
                u.update_processing_config(processing_config)

    def setup(self, win):
        for i, u in enumerate(self.child_updaters):
            sublayout = win.addLayout(row=0, col=i)
            u.setup(sublayout)

    def update(self, data):
        for u, d in zip(self.child_updaters, data):
            u.update(d)


class MultiSensorPGUpdaterCreator:
    def __init__(self, updater_class):
        self.updater_class = updater_class

    def create_pg_updater(self, sensor_config, processing_config, session_info):
        return CompositePGUpdater(
            sensor_config, processing_config, session_info, self.updater_class
        )
