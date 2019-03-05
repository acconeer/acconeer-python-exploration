import queue


class DemoControl:
    def __init__(self):
        self.last_gui_state = ""
        self.internal_state = None
        self.out_queues = []
        self.input_queue = queue.Queue()
        self.detector_started = False
        self.detectors = {}
        self.detector_thread = None
        self.robot_control = None
        self.streaming_client_args = None

    def add_detector(self, detector_class):
        self.detectors[detector_class.detector_name] = detector_class
        print("Adding detector", detector_class.detector_name)

    def set_streaming_client_args(self, args):
        self.streaming_client_args = args

    def start_detector(self, name, params):
        if self.detector_thread is not None:
            if self.detector_thread.detector_name != name:
                return {"error": "other detector active",
                        "active_detector": self.detector_thread.detector_name}
            else:
                return {"ok": "already started"}
        if not (name in self.detectors):
            return {"error": "unknown detector"}
        self.detector_thread = self.detectors[name](self, params)
        self.detector_thread.start()
        print("Detector %s started" % name)
        return {"ok": None}

    def stop_detector(self):
        if self.detector_thread is None:
            return {"error": "no detector active"}
        self.detector_thread.stop()
        self.detector_thread = None
        return {"ok": None}

    def process_next(self):
        cmd = self.input_queue.get()
        if type(cmd) == list and len(cmd) > 0:
            if cmd[0] == "robot_command":
                print("demo_control: got robot_command")
                if self.robot_control is not None:
                    self.robot_control.handle_command(cmd[1:])
                else:
                    print("demo_control: got rvc_command but rvc control not initiated")
            elif cmd[0] == "exit":
                if self.detector_thread:
                    self.stop_detector(self.detector_thread.name)
                return False
        elif cmd is not None:
            self._update_gui_state(cmd)
        return True

    def subscribe(self):
        q = queue.Queue()
        q.put(self.last_gui_state)
        self.out_queues.append(q)

        # Clean up old (hopefully) unused output queues
        self.out_queues = [x for x in self.out_queues if x.qsize() < 5]
        return q

    def put_cmd(self, cmd):
        self.input_queue.put(cmd)

    def _update_gui_state(self, mess):
        self.last_gui_state = mess
        for q in self.out_queues:
            q.put(mess)
