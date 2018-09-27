import sys
import socket
import json
from array import array
from copy import deepcopy
import numpy as np


class StreamingClient:
    ENVELOPE_DATA_TYPE = "envelope_data"
    IQ_DATA_TYPE = "iq_data"
    KNOWN_DATA_TYPES = [ENVELOPE_DATA_TYPE, IQ_DATA_TYPE]

    def __init__(self, host, port=6110):
        self.host = host
        self.port = port

    def run_session(self, config, data_callback):
        config = deepcopy(config)
        config["output_format"] = "json+binary"

        self.recv_buf = bytearray()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setblocking(True)
        self.sock.settimeout(3)
        self.sock.connect((self.host, self.port))

        self._send_data(config)

        while True:
            metadata, payload = self._recv_data()
            if metadata["status"] == "ok":
                try:
                    if not data_callback(metadata, payload):
                        break
                except Exception as e:
                    self.sock.close()
                    raise e
            else:
                break

        self.sock.close()

    def _send_data(self, data):
        json_data = json.dumps(data, separators=(",", ":"))
        self.sock.sendall(bytes(json_data + "\n", "ascii"))

    def _recv_data(self):
        metadata_buf = []
        while True:
            if len(self.recv_buf) > 0:
                b = self.recv_buf.pop(0)
                c = chr(b)
                metadata_buf.append(c)
                if c == '\n':
                    break
            else:
                self.recv_buf.extend(bytearray(self.sock.recv(4096)))

        metadata = json.loads("".join(metadata_buf))
        payload_size = metadata["payload_size"]

        if payload_size > 0:
            while len(self.recv_buf) < payload_size:
                self.recv_buf.extend(bytearray(self.sock.recv(4096)))

            packed = self.recv_buf[:payload_size]
            self.recv_buf = self.recv_buf[len(packed):]

            data_type = metadata["type"]
            if data_type in self.KNOWN_DATA_TYPES:
                payload_array = array("h")  # signed short
            else:  # fallback
                payload_array = array("H")  # unsigned short

            payload_array.fromstring(packed)
            if sys.byteorder == "little":
                payload_array.byteswap()
            payload = np.array(payload_array, dtype="float")

            num_vals = metadata["data_size"]
            num_sens = metadata["data_sensors"]

            if data_type == self.IQ_DATA_TYPE:
                payload = payload.reshape((2, num_vals*num_sens), order="F").view(dtype="complex")[0, ...]

            payload = np.reshape(payload, (num_sens, num_vals))
        else:
            payload = None

        return metadata, payload
