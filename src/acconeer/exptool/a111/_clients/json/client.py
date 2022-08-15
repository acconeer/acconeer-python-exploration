# Copyright (c) Acconeer AB, 2022
# All rights reserved

import enum
import json
import logging
import warnings
from copy import deepcopy
from time import time

import numpy as np

from acconeer.exptool.a111._clients import links
from acconeer.exptool.a111._clients.base import (
    BaseClient,
    ClientError,
    SessionSetupError,
    decode_version_str,
)
from acconeer.exptool.a111._modes import Mode, get_mode


log = logging.getLogger(__name__)


class JsonProtocolBase:
    def __init__(self, link):
        self._link = link
        self._num_sensors = None
        self._sweeps_per_frame = None
        self._session_cmd = None
        self._mode = None

    def _send_cmd(self, cmd_dict):
        cmd_dict["api_version"] = 3
        s = json.dumps(cmd_dict, separators=(",", ":"))
        packed = bytearray(s + "\n", "ascii")

        self._link.send(packed)

    def _recv_frame(self):
        packed = self._link.recv_until(b"\n")
        header = json.loads(str(packed, "ascii"))
        payload_len = header["payload_size"]

        if payload_len > 0:
            payload = self._link.recv(payload_len)
        else:
            payload = None

        return header, payload

    def get_version(self):
        cmd = {"cmd": "get_version"}
        self._send_cmd(cmd)

        try:
            header, _ = self._recv_frame()
        except links.LinkError as e:
            raise ClientError("no response from server") from e

        log.debug("connected and got a response")

        msg = None
        if header["status"] == "ok":
            msg = header["message"].lower()
            log.info("version msg: {}".format(msg))
        else:
            log.info("No get_version cmd, try get_system_info")

        return msg

    def get_sensor_count(self):
        self._send_cmd({"cmd": "get_board_sensor_count"})
        header, _ = self._recv_frame()
        return int(header["message"])

    def setup_session(self, config):
        pass

    def init_session(self, retry=True):
        pass

    def start_session(self):
        if not self._session_ready:
            self.init_session()

        cmd = {"cmd": "start_streaming"}
        self._send_cmd(cmd)
        header, _ = self._recv_frame()
        if header["status"] != "start":
            raise ClientError

        log.debug("started streaming")

    def get_next(self):
        header, payload = self._recv_frame()

        status = header["status"]
        if status == "end":
            raise ClientError("session ended")
        elif status != "ok":
            raise ClientError("server error")

        info = self.decode_stream_header(header)
        data = self.decode_stream_payload(payload)
        return info, data

    def stop_session(self):
        pass

    def decode_stream_header(self, header):
        pass

    def decode_stream_payload(self, payload):
        pass


class JsonProtocolStreamingServer(JsonProtocolBase):
    def __init__(self, link, squeeze):
        super().__init__(link)
        self._squeeze = squeeze
        # stacklevel=5 will warn user code as deprecated.
        # (JsonPSS -> SocketClient -> ClientFactory -> Client -> <user code>)
        warnings.warn(
            "Streaming Server is deprecated. Consider upgrading to Exploration Server.",
            DeprecationWarning,
            stacklevel=5,
        )

    def setup_session(self, config):
        if isinstance(config, dict):
            cmd = deepcopy(config)
            log.warning("setup with raw dict config - you're on your own")
        else:
            cmd = self._get_dict_for_config(config)

        try:
            self._mode = get_mode(cmd["cmd"].lower().replace("_data", ""))
        except ValueError:
            self._mode = None

        self._sweeps_per_frame = cmd.get("sweeps_per_frame", 16)
        self._num_sensors = len(cmd["sensors"])

        cmd["output_format"] = "json+binary"
        self._session_cmd = cmd

        return cmd

    def init_session(self, retry=True):
        if self._session_cmd is None:
            raise ClientError

        self._send_cmd(self._session_cmd)
        header, _ = self._recv_frame()

        if header["status"] == "error":
            if retry:
                return self.init_session(retry=False)
            else:
                raise SessionSetupError
        elif header["status"] != "ok":
            raise ClientError("got unexpected header")

        log.debug("session initialized")

        self._session_ready = True
        info = self._get_session_info_for_header(header)

        return info

    def stop_session(self):
        cmd = {"cmd": "stop_streaming"}
        self._send_cmd(cmd)

        t0 = time()
        while time() - t0 < self._link.timeout:
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

        self._link.timeout = self._link.DEFAULT_TIMEOUT

        self._session_ready = False

        log.debug("stopped streaming")

    def decode_stream_header(self, header):
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

    def decode_stream_payload(self, payload):
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

    def _get_dict_for_config(self, config):
        d = {}
        d["cmd"] = get_mode(config.mode).value.lower() + "_data"

        for config_key, cmd_key in CONFIG_TO_CMD_KEY_MAP.items():
            config_val = getattr(config, config_key, None)

            if self._mode == Mode.IQ and config_key == "sampling_mode":
                continue

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

    def _get_session_info_for_header(self, header):
        info = {}

        for header_key, val in header.items():
            info_key = SESSION_HEADER_TO_INFO_KEY_REMAP.get(header_key, header_key)

            if info_key is None:
                continue

            info[info_key] = val

        return info

    @property
    def squeeze(self):
        return self._squeeze

    @squeeze.setter
    def squeeze(self, squeeze):
        self._squeeze = squeeze


class JsonProtocolExplorationServer(JsonProtocolBase):
    def __init__(self, link, squeeze):
        super().__init__(link)
        self._squeeze = squeeze

    def get_system_info(self):
        self._send_cmd({"cmd": "get_system_info"})
        try:
            header, _ = self._recv_frame()
        except links.LinkError as e:
            raise ClientError("no response from server") from e

        if header["status"] != "ok":
            raise ClientError(f"system_info error {header}")

        system_info = header["system_info"]
        return system_info

    def _set_baudrate(self, baudrate):
        set_baudrate_cmd = {"cmd": "set_uart_baudrate", "baudrate": baudrate}
        self._send_cmd(set_baudrate_cmd)
        try:
            header, _ = self._recv_frame()
        except links.LinkError as e:
            raise ClientError("no response from server") from e

        if header["status"] == "ok":
            self._link.baudrate = baudrate

    def setup_session(self, config):
        if isinstance(config, dict):
            cmd = deepcopy(config)
            log.warning("setup with raw dict config - you're on your own")
            return cmd

        cmd = {}
        cmd["cmd"] = "setup"
        service = get_mode(config.mode).value.lower()
        self._mode = get_mode(config.mode)

        update_rate = getattr(config, "update_rate", None)
        if update_rate:
            cmd["update_rate"] = update_rate

        repetition_mode = getattr(config, "repetition_mode", None)
        if repetition_mode:
            cmd["repetition_mode"] = repetition_mode.json_value

        cmd["groups"] = []
        cmd["groups"].append([])

        sensors = getattr(config, "sensor", None)
        sensor_config = {}

        for config_key, cmd_key in CONFIG_TO_CMD_KEY_MAP.items():
            config_val = getattr(config, config_key, None)

            if config_key in ["sensor", "update_rate", "repetition_mode"]:
                continue

            if self._mode == Mode.IQ and config_key == "sampling_mode":
                continue

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

            sensor_config[cmd_key] = cmd_val

        for sensor in sensors:
            sensor_setup = {}
            sensor_setup["sensor_id"] = sensor
            sensor_setup["service"] = service
            sensor_setup["config"] = sensor_config
            cmd["groups"][0].append(sensor_setup)

        self._sweeps_per_frame = cmd["groups"][0][0]["config"].get("sweeps_per_frame", 16)
        self._num_sensors = len(sensors)

        self._session_cmd = cmd

        return cmd

    def init_session(self, retry=True):
        if self._session_cmd is None:
            raise ClientError

        self._send_cmd(self._session_cmd)
        header, _ = self._recv_frame()

        if header["status"] == "error":
            if retry:
                return self.init_session(retry=False)
            else:
                raise SessionSetupError
        elif header["status"] != "ok":
            raise ClientError("got unexpected header")

        log.debug("session initialized")

        self._session_ready = True

        info = {}

        for header_key, val in header["metadata"][0][0].items():
            info_key = SESSION_HEADER_TO_INFO_KEY_REMAP.get(header_key, header_key)

            if info_key is None:
                continue

            info[info_key] = val

        return info

    def stop_session(self):
        cmd = {"cmd": "stop_streaming"}
        self._send_cmd(cmd)

        t0 = time()
        while time() - t0 < self._link.timeout:
            header, _ = self._recv_frame()
            status = header["status"]
            if status == "stop":
                break
            elif status == "ok":  # got streaming data
                continue
            else:
                raise ClientError
        else:
            raise ClientError

        self._link.timeout = self._link.DEFAULT_TIMEOUT

        self._session_ready = False

        log.debug("stopped streaming")

    def decode_stream_header(self, header):
        raw_infos = header["result_info"][0]
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

    def decode_stream_payload(self, payload):
        if not payload:
            return None

        squeeze = self.squeeze and self._num_sensors == 1

        if self._mode == Mode.SPARSE:
            data = np.frombuffer(payload, dtype="<u2").astype("float")

            if squeeze:
                shape = (self._sweeps_per_frame, -1)
            else:
                shape = (self._num_sensors, self._sweeps_per_frame, -1)

            return data.reshape(shape)

        if self._mode == Mode.IQ:
            data = np.frombuffer(payload, dtype="<i2").astype("float")
            data = data.reshape((-1, 2)).view(dtype="complex").flatten()
        elif self._mode in (Mode.ENVELOPE, Mode.POWER_BINS):
            data = np.frombuffer(payload, dtype="<u2").astype("float")
        else:  # Fallback
            data = np.frombuffer(payload, dtype="<u2")

        if not squeeze:
            data = data.reshape((self._num_sensors, -1))

        return data

    @property
    def squeeze(self):
        return self._squeeze

    @squeeze.setter
    def squeeze(self, squeeze):
        self._squeeze = squeeze


class SocketClient(BaseClient):
    def __init__(self, host, serial_link=False, override_baudrate=None, **kwargs):
        super().__init__(**kwargs)

        if serial_link:
            self._link = links.ExploreSerialLink(host)
        else:
            self._link = links.SocketLink(host)
        self._protocol = None
        self._override_baudrate = override_baudrate

    def _connect(self):
        info = {}

        self._link.connect()

        self._protocol = JsonProtocolBase(self._link)

        msg = self._protocol.get_version()
        if msg:
            startstr = "server version "
            if not msg.startswith(startstr):
                log.warning("server version unknown")
                return info

            server_version_str = msg[len(startstr) :].strip()
            info.update(decode_version_str(server_version_str))

            self._protocol = JsonProtocolStreamingServer(self._link, self.squeeze)
            info["board_sensor_count"] = self._protocol.get_sensor_count()
        else:
            self._protocol = JsonProtocolExplorationServer(self._link, self.squeeze)
            system_info = self._protocol.get_system_info()
            info.update(decode_version_str(system_info["rss_version"]))
            info["sensor"] = system_info["sensor"]
            info["board_sensor_count"] = system_info["sensor_count"]
            info["hw"] = system_info["hw"]

            # Set new baudrate if the link is of ExploreSerialLink type and
            # the baudrate is overriden with a value > 0
            # if the server reports max_baudrate > 0
            baudrate = self._override_baudrate or system_info.get("max_baudrate")
            if isinstance(self._link, links.ExploreSerialLink) and baudrate:
                self._protocol._set_baudrate(baudrate)

        return info

    def _setup_session(self, config):
        cmd = self._protocol.setup_session(config)
        info = self._init_session()

        if "update_rate" in cmd:
            self._link.timeout = 1 / cmd["update_rate"] + self._link.DEFAULT_TIMEOUT
        else:
            self._link.timeout = self._link.DEFAULT_TIMEOUT

        log.debug("setup session")

        return info

    def _start_session(self):
        self._protocol.start_session()

    def _get_next(self):
        return self._protocol.get_next()

    def _stop_session(self):
        self._protocol.stop_session()

    def _disconnect(self):
        self._link.disconnect()

        log.debug("disconnected")

    def _init_session(self, retry=True):
        return self._protocol.init_session()

    @property
    def squeeze(self):
        return self._squeeze

    @squeeze.setter
    def squeeze(self, squeeze):
        if self._protocol:
            self._protocol.squeeze = squeeze
        self._squeeze = squeeze

    @property
    def description(self):
        if isinstance(self._link, links.ExploreSerialLink):
            return f"UART ({self._link._port})"
        else:
            return f"socket ({self._link._host})"


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
    "asynchronous_measurement": "asynchronous_measurement",
    "mur": "mur",
}

SESSION_HEADER_TO_INFO_KEY_REMAP = {
    "status": None,
    "payload_size": None,
    "start_m": "range_start_m",
    "length_m": "range_length_m",
}

DATA_HEADER_TO_INFO_KEY_REMAP = {}
