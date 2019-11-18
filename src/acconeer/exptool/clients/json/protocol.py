from collections.abc import Iterable
from collections import namedtuple
import json
import numpy as np

from acconeer.exptool.clients.base import ClientError


KeyConfigAttrPair = namedtuple("KeyConfigAttrPair", ["key", "config_attr", "required"])


KEY_AND_CONFIG_ATTR_PAIRS = [
    KeyConfigAttrPair("sensors", "sensor", True),
    KeyConfigAttrPair("start_range", "range_start", True),
    KeyConfigAttrPair("end_range", "range_end", True),
    KeyConfigAttrPair("frequency", "sweep_rate", True),
    KeyConfigAttrPair("gain", "gain", False),
    KeyConfigAttrPair("bin_count", "bin_count", False),
    KeyConfigAttrPair("running_average_factor", "running_average_factor", False),
    KeyConfigAttrPair("compensate_phase", "compensate_phase", False),
    KeyConfigAttrPair("profile", "session_profile", False),
    KeyConfigAttrPair("enable_stitching", "experimental_stitching", False),
    KeyConfigAttrPair("sweeps_per_result", "number_of_subsweeps", False),
    KeyConfigAttrPair("sampling_mode", "sampling_mode", False),
    KeyConfigAttrPair("point_average", "hw_accelerated_average_samples", False),
    KeyConfigAttrPair("sweep_rate", "subsweep_rate", False),
    KeyConfigAttrPair("stepsize", "stepsize", False),
]

MODE_TO_CMD_MAP = {
    "power_bin": "power_bins_data",
    "envelope": "envelope_data",
    "iq": "iq_data",
    "sparse": "sparse_data",
}

# None = ignore value
SESSION_HEADER_TO_INFO_KEY_MAP = {
    "data_length": "data_length",
    "actual_start_m": "actual_range_start",
    "actual_length_m": "actual_range_length",
    "status": None,
    "payload_size": None,
    "free_space_absolute_offset": None,
    "sweeps_per_result": "number_of_subsweeps",
    "actual_sweep_rate": "actual_subsweep_rate",
    "actual_stepsize_m": "actual_stepsize",
}

# None = ignore value
STREAM_HEADER_TO_INFO_KEY_MAP = {
    "sequence_number": "sequence_number",
    "data_saturated": "data_saturated",
    "data_size": None,
    "data_sensors": None,
    "type": None,
    "status": None,
    "payload_size": None,
}


def get_dict_for_config(config):
    d = {}
    d["cmd"] = MODE_TO_CMD_MAP[config.mode]
    for pair in KEY_AND_CONFIG_ATTR_PAIRS:
        config_val = getattr(config, pair.config_attr, None)
        if config_val is None:
            if pair.required:
                raise ClientError("{} needs to be set in config".format(pair.config_attr))
        else:
            if isinstance(config_val, bool):
                d[pair.key] = int(config_val)
            else:
                d[pair.key] = config_val
    return d


def get_session_info_for_header(header):
    info = {}
    for header_k, v in header.items():
        try:
            info_k = SESSION_HEADER_TO_INFO_KEY_MAP[header_k]
        except KeyError:
            info_k = header_k

        if info_k is not None:
            info[info_k] = v
    return info


def decode_stream_frame(header, payload, squeeze, number_of_subsweeps=None):
    info = decode_stream_header(header, squeeze)
    data = decode_stream_payload(header, payload, squeeze, number_of_subsweeps)
    return info, data


def decode_stream_header(header, squeeze):
    num_sensors = header["data_sensors"]
    infos = [dict() for _ in range(num_sensors)]

    for header_k, v in header.items():
        try:
            info_k = STREAM_HEADER_TO_INFO_KEY_MAP[header_k]
        except KeyError:
            info_k = header_k

        if info_k is not None:
            if isinstance(v, Iterable):
                for info, e in zip(infos, v):
                    info[info_k] = e
            else:
                for info in infos:
                    info[info_k] = v

    return infos[0] if (squeeze and num_sensors == 1) else infos


def decode_stream_payload(header, payload, squeeze, num_subsweeps=None):
    if not payload:
        return None

    num_points = header["data_size"]
    num_sensors = header["data_sensors"]
    sweep_type = header["type"]

    squeeze = squeeze and num_sensors == 1

    if sweep_type == "iq_data":
        sweep = np.frombuffer(payload, dtype=">i2").astype("float")
        sweep *= 2**(-12)
        n = num_points * num_sensors
        sweep = sweep.reshape((2, n), order="F").view(dtype="complex").flatten()
    elif sweep_type == "envelope_data":
        sweep = np.frombuffer(payload, dtype=">u2").astype("float")
    elif sweep_type == "sparse_data":
        sweep = np.frombuffer(payload, dtype=">u2").astype("float")
        sweep -= 2**15

        if squeeze:
            sweep = sweep.reshape((num_subsweeps, -1))
        else:
            sweep = sweep.reshape((num_sensors, num_subsweeps, -1))

        return sweep
    else:  # Fallback
        sweep = np.frombuffer(payload, dtype=">u2")

    if not squeeze:
        sweep = sweep.reshape((num_sensors, num_points))

    return sweep


def pack(unpacked):
    s = json.dumps(unpacked, separators=(",", ":"))
    return bytearray(s + "\n", "ascii")


def unpack(packed):
    s = str(packed, "ascii")
    return json.loads(s)
