import enum
import json
import logging
from copy import deepcopy
from time import time

import numpy as np

from acconeer.exptool.clients import links
from acconeer.exptool.clients.base import (
    BaseClient,
    ClientError,
    SessionSetupError,
    decode_version_str,
)
from acconeer.exptool.modes import Mode, get_mode


log = logging.getLogger(__name__)


class SocketClient(BaseClient):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)

        self._link = links.SocketLink(host)

        self._session_cmd = None
        self._session_ready = False
        self._mode = None
        self._sweeps_per_frame = None
        self._num_sensors = None

    def _connect(self):
        info = {}

        self._link.connect()

        cmd = {"cmd": "get_version"}
        self._send_cmd(cmd)

        try:
            header, _ = self._recv_frame()
        except links.LinkError as e:
            raise ClientError("no response from server") from e

        log.debug("connected and got a response")

        if header["status"] != "ok":
            raise ClientError("server error while connecting")

        msg = header["message"].lower()
        log.info("version msg: {}".format(msg))

        startstr = "server version v"
        if not msg.startswith(startstr):
            log.warning("server version unknown")
            return info

        server_version_str = msg[len(startstr):].strip()
        info.update(decode_version_str(server_version_str))

        self._send_cmd({"cmd": "get_board_sensor_count"})
        header, _ = self._recv_frame()
        info["board_sensor_count"] = int(header["message"])

        return info

    def _setup_session(self, config):
        if isinstance(config, dict):
            cmd = deepcopy(config)
            log.warning("setup with raw dict config - you're on your own")
        else:
            cmd = get_dict_for_config(config)

        try:
            self._mode = get_mode(cmd["cmd"].lower().replace("_data", ""))
        except ValueError:
            self._mode = None

        self._sweeps_per_frame = cmd.get("sweeps_per_frame", 16)
        self._num_sensors = len(cmd["sensors"])

        cmd["output_format"] = "json+binary"

        self._session_cmd = cmd
        info = self._init_session()

        log.debug("setup session")

        return info

    def _start_session(self):
        if not self._session_ready:
            self._init_session()

        cmd = {"cmd": "start_streaming"}
        self._send_cmd(cmd)
        header, _ = self._recv_frame()
        if header["status"] != "start":
            raise ClientError

        log.debug("started streaming")

    def _get_next(self):
        header, payload = self._recv_frame()

        status = header["status"]
        if status == "end":
            raise ClientError("session ended")
        elif status != "ok":
            raise ClientError("server error")

        info = self._decode_stream_header(header)
        data = self._decode_stream_payload(payload)
        return info, data

    def _stop_session(self):
        cmd = {"cmd": "stop_streaming"}
        self._send_cmd(cmd)

        t0 = time()
        while time() - t0 < self._link._timeout:
            header, _ = self._recv_frame()
            status = header["status"]
            if status == "end":
                break
            elif status == "ok":  # got streaming data
                continue
            else:
                raise ClientError
        else:
            raise ClientError

        self._session_ready = False

        log.debug("stopped streaming")

    def _disconnect(self):
        self._link.disconnect()
        self._session_cmd = None
        self._session_ready = False

        log.debug("disconnected")

    def _init_session(self, retry=True):
        if self._session_cmd is None:
            raise ClientError

        self._send_cmd(self._session_cmd)
        header, _ = self._recv_frame()

        if header["status"] == "error":
            if retry:
                return self._init_session(retry=False)
            else:
                raise SessionSetupError
        elif header["status"] != "ok":
            raise ClientError("got unexpected header")

        log.debug("session initialized")

        self._session_ready = True
        info = get_session_info_for_header(header)
        return info

    def _send_cmd(self, cmd_dict):
        cmd_dict["api_version"] = 3
        s = json.dumps(cmd_dict, separators=(",", ":"))
        packed = bytearray(s + "\n", "ascii")

        self._link.send(packed)

    def _recv_frame(self):
        packed = self._link.recv_until(b'\n')
        header = json.loads(str(packed, "ascii"))
        payload_len = header["payload_size"]

        if payload_len > 0:
            payload = self._link.recv(payload_len)
        else:
            payload = None

        return header, payload

    def _decode_stream_header(self, header):
        raw_infos = header["result_info"]
        mapped_infos = [{} for _ in raw_infos]

        for (raw_info, mapped_info) in zip(raw_infos, mapped_infos):
            for raw_key, val in raw_info.items():
                mapped_key = DATA_HEADER_TO_INFO_KEY_REMAP.get(raw_key, raw_key)

                if mapped_key is None:
                    continue

                mapped_info[mapped_key] = val

        if self.squeeze and len(mapped_infos) == 1:
            return mapped_infos[0]
        else:
            return mapped_infos

    def _decode_stream_payload(self, payload):
        if not payload:
            return None

        squeeze = self.squeeze and self._num_sensors == 1

        if self._mode == Mode.SPARSE:
            data = np.frombuffer(payload, dtype=">u2").astype("float")

            if squeeze:
                shape = (self._sweeps_per_frame, -1)
            else:
                shape = (self._num_sensors, self._sweeps_per_frame, -1)

            return data.reshape(shape)

        if self._mode == Mode.IQ:
            data = np.frombuffer(payload, dtype=">i2").astype("float")
            data = data.reshape((-1, 2)).view(dtype="complex").flatten()
        elif self._mode in (Mode.ENVELOPE, Mode.POWER_BINS):
            data = np.frombuffer(payload, dtype=">u2").astype("float")
        else:  # Fallback
            data = np.frombuffer(payload, dtype=">u2")

        if not squeeze:
            data = data.reshape((self._num_sensors, -1))

        return data


def get_dict_for_config(config):
    d = {}
    d["cmd"] = get_mode(config.mode).value.lower() + "_data"

    for config_key, cmd_key in CONFIG_TO_CMD_KEY_MAP.items():
        config_val = getattr(config, config_key, None)

        if config_val is None:
            continue

        if isinstance(config_val, bool):
            cmd_val = int(config_val)
        elif isinstance(config_val, enum.Enum):
            if hasattr(config_val, "json_value"):
                cmd_val = config_val.json_value
            else:
                cmd_val = config_val.value
        else:
            cmd_val = config_val

        d[cmd_key] = cmd_val

    return d


def get_session_info_for_header(header):
    info = {}

    for header_key, val in header.items():
        info_key = SESSION_HEADER_TO_INFO_KEY_REMAP.get(header_key, header_key)

        if info_key is None:
            continue

        info[info_key] = val

    return info


CONFIG_TO_CMD_KEY_MAP = {
    "sensor": "sensors",
    "range_start": "range_start",
    "range_length": "range_length",
    "repetition_mode": "repetition_mode",
    "update_rate": "update_rate",
    "gain": "gain",
    "hw_accelerated_average_samples": "hw_accelerated_average_samples",
    "profile": "profile",
    "bin_count": "bin_count",
    "downsampling_factor": "downsampling_factor",
    "noise_level_normalization": "noise_level_normalization",
    "maximize_signal_attenuation": "maximize_signal_attenuation",
    "running_average_factor": "running_average_factor",
    "sampling_mode": "sampling_mode",
    "sweeps_per_frame": "sweeps_per_frame",
    "sweep_rate": "sweep_rate",
    "tx_disable": "tx_disable",
    "power_save_mode": "power_save_mode",
    "depth_lowpass_cutoff_ratio": "depth_lowpass_cutoff_ratio",
    "asynchronous_measurement" : "asynchronous_measurement",
}

SESSION_HEADER_TO_INFO_KEY_REMAP = {
    "status": None,
    "payload_size": None,
    "start_m": "range_start_m",
    "length_m": "range_length_m",
}

DATA_HEADER_TO_INFO_KEY_REMAP = {
}
