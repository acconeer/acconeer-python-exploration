import json
import numpy as np
from threading import Thread
from acconeer_utils.clients.reg.client import RegClient
from acconeer_utils.clients.json.client import JSONClient
from acconeer_utils.clients import configs
from acconeer_utils import example_utils


class Detector(Thread):
    connection_checked = False

    def __init__(self, demo_ctrl, name):
        super().__init__(name=name)
        self.terminating = False
        self._demo_ctrl = demo_ctrl
        self.alive = False

    def run(self):
        print("#### New thread for %s" % self.name)

        args = self._demo_ctrl.streaming_client_args
        print("args:", args)

        example_utils.config_logging(args)

        if args.socket_addr:
            client = JSONClient(args.socket_addr)
        else:
            port = args.serial_port or example_utils.autodetect_serial_port()
            client = RegClient(port)

        try:
            client.connect()
        except Exception as e:
            print("Got exception:", e)

        session_info = client.setup_session(self.config)
        print("Session info:\n", session_info, "\n")

        client.start_streaming()
        while not self.terminating:
            sweep_info, sweep_data = client.get_next()

            d = self.process_data(sweep_data)
            if d is not None:
                self._demo_ctrl.put_cmd(str(d))
            if self.terminating:
                break
        client.disconnect()

    def stop(self):
        self.alive = False
        self.terminating = True
        self.join()
        print("%s stream stopped" % self.name)

    def process_data(self, line):
        print("default data processing")
        return {"unknown": line}

    def update_config(self, params):
        args = self._demo_ctrl.streaming_client_args
        self.config.sensor = args.sensors

        self.config.sweep_rate = 10

        if "range_start" in params and "range_end" in params:
            self.config.range_interval = [float(params["range_start"]), float(params["range_end"])]
        if "frequency" in params:
            self.config.sweep_rate = float(params["frequency"])
        if "gain" in params:
            self.config.gain = float(params["gain"])
        if "average" in params:
            self.config.running_average_factor = float(params["average"])


class PowerBinHandler(Detector):
    detector_name = "powerbins"

    def __init__(self, demo_ctrl, params):
        super().__init__(demo_ctrl, self.detector_name)

        self.config = configs.PowerBinServiceConfig()
        self.update_config(params)

        if "bins" in params:
            self.config.bin_count = int(params["bins"])

    def process_data(self, a):
        data = [round(float(x)) for x in a[1:]]
        return json.dumps({"powerbins": data})


class EnvelopeHandler(Detector):
    detector_name = "envelope"

    def __init__(self, demo_ctrl, params):
        super().__init__(demo_ctrl, self.detector_name)

        self.config = configs.EnvelopeServiceConfig()

        self.update_config(params)

        if "profile" in params:
            if params["profile"] == "0":
                self.config.session_profile = configs.EnvelopeServiceConfig.MAX_SNR
            elif params["profile"] == "1":
                self.config.session_profile = configs.EnvelopeServiceConfig.MAX_DEPTH_RESOLUTION
            else:
                print("Unknown profile")

    def process_data(self, a):
        data = [round(int(x)) for x in a[1:]]
        return json.dumps({"envelope": data})


class IQHandler(Detector):
    detector_name = "iq"

    def __init__(self, demo_ctrl, params):
        super().__init__(demo_ctrl, self.detector_name)
        self.config = configs.IQServiceConfig()
        self.update_config(params)

    def process_data(self, a):
        response = []
        for z in a.tolist()[0::18]:
            response.append({"re": np.real(z), "im": np.imag(z)})
        return json.dumps({"iq": response})
