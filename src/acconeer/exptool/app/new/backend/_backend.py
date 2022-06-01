import multiprocessing as mp


class Backend:
    def __init__(self):
        self._recv_queue: mp.Queue = mp.Queue()
        self._send_queue: mp.Queue = mp.Queue()
        self._stop_event = mp.Event()
        self._process = mp.Process(
            target=process_program,
            args=(
                self._send_queue,
                self._recv_queue,
                self._stop_event,
            ),
            daemon=True,
        )

    def start(self):
        self._process.start()

    def stop(self):
        self._stop_event.set()
        self.send("stop")
        self._process.join()
        self._process.close()

    def send(self, message):
        self._send_queue.put(message)

    def recv(self, message):
        self._recv_queue.get(message)


def process_program(recv_queue, send_queue, stop_event):
    try:
        while not stop_event.is_set():
            msg = recv_queue.get()

            if msg == "stop":
                break

            ...
    finally:
        recv_queue.close()
        send_queue.close()
