from types import ModuleType


class PassthroughProcessor:
    def __init__(self, sensor_config, processing_config, session_info):
        pass

    def process(self, data, data_info):
        return data


def multi_sensor_wrap(module: ModuleType) -> ModuleType:
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
