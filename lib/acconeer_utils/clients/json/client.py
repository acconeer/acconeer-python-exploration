from time import time
from copy import deepcopy
import logging
from distutils.version import StrictVersion

from acconeer_utils.clients.base import BaseClient, ClientError
from acconeer_utils.clients import links
from acconeer_utils.clients.json import protocol


log = logging.getLogger(__name__)

MIN_VERSION = StrictVersion("1.5.2")
DEV_VERSION = StrictVersion("1.9.1")


class JSONClient(BaseClient):
    def __init__(self, host, **kwargs):
        super().__init__(**kwargs)

        self._link = links.SocketLink(host)

        self._session_cmd = None
        self._session_ready = False
        self._num_subsweeps = None

    def _connect(self):
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
            return

        server_version_str = msg[len(startstr):].strip()

        try:
            server_version = StrictVersion(server_version_str)
        except ValueError:
            log.warning("server version unknown")
            return

        if server_version < MIN_VERSION:
            log.warning("server version is not supported (too old)")
        elif server_version != DEV_VERSION:
            log.warning("server version might not be fully supported")

    def _setup_session(self, config):
        if isinstance(config, dict):
            cmd = deepcopy(config)
            log.warning("setup with raw dict config - you're on your own")
        else:
            cmd = protocol.get_dict_for_config(config)

        cmd["output_format"] = "json+binary"

        self._session_cmd = cmd
        info = self._init_session()

        log.debug("setup session")

        return info

    def _start_streaming(self):
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

        return protocol.decode_stream_frame(header, payload, self.squeeze, self._num_subsweeps)

    def _stop_streaming(self):
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
                raise ClientError("server error while initializing session")
        elif header["status"] != "ok":
            raise ClientError("got unexpected header")

        log.debug("session initialized")

        self._session_ready = True
        info = protocol.get_session_info_for_header(header)
        self._num_subsweeps = info.get("number_of_subsweeps")
        return info

    def _send_cmd(self, cmd_dict):
        cmd_dict["api_version"] = 2
        packed = protocol.pack(cmd_dict)
        self._link.send(packed)

    def _recv_frame(self):
        packed_header = self._link.recv_until(b'\n')
        header = protocol.unpack(packed_header)
        payload_len = header["payload_size"]
        if payload_len > 0:
            payload = self._link.recv(payload_len)
        else:
            payload = None
        return header, payload
