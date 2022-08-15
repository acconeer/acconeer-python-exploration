# Copyright (c) Acconeer AB, 2022
# All rights reserved

import enum
import importlib.resources
import operator
from functools import partial, reduce

import attr
import yaml

from acconeer.exptool.a111 import _configs
from acconeer.exptool.a111._modes import Mode, get_mode

from . import data


BYTEORDER = "little"
BO = BYTEORDER


class Category(enum.Enum):
    GENERAL = "general"
    CONFIG = "config"
    SESSION_INFO = "metadata"
    DATA_INFO = "result_info"
    RESULT = "result"


class DataType(enum.Enum):
    BITSET = "bitmask"
    ENUM = "enum"
    BOOL = "boolean"
    UINT16 = "uint16"
    UINT32 = "uint32"
    INT32 = "int32"


@attr.s
class Register:
    full_name = attr.ib()
    stripped_name = attr.ib()
    addr = attr.ib()
    modes = attr.ib()
    readable = attr.ib()
    writable = attr.ib()
    category = attr.ib()
    data_type = attr.ib()

    float_scale = attr.ib(default=None)  # Applicable iff float, if not None then decode as float

    enum = attr.ib(default=None)
    bitset_flags = attr.ib(default=None)
    bitset_masks = attr.ib(default=None)

    def encode(self, value):
        if self.data_type == DataType.BITSET:
            try:
                x = int(self.bitset_flags(value))
            except ValueError:
                if isinstance(value, str):
                    x = self.bitset_flags[value.upper()].value
                else:
                    xs = [self.bitset_flags[v.upper()].value for v in value] + [0]
                    x = reduce(operator.or_, xs)

            return x.to_bytes(4, BO)

        if self.data_type == DataType.ENUM:
            if isinstance(value, enum.Enum) and not isinstance(value, self.enum):
                value = ENUM_REMAP.get(value, value.name)

            if isinstance(value, str):
                value = self.enum[value.upper()]
            elif isinstance(value, int):
                value = self.enum(value)

            if not isinstance(value, self.enum):
                raise ValueError

            return value.value.to_bytes(4, BO)

        if self.data_type == DataType.BOOL:
            return int(bool(value)).to_bytes(4, BO)

        if self.float_scale is not None:
            value = round(value * self.float_scale)

        value = int(value)
        signed = self.data_type == DataType.INT32

        if not signed and value < 0:
            raise ValueError

        return value.to_bytes(4, BO, signed=signed)

    def decode(self, value):
        signed = self.data_type == DataType.INT32
        value = int.from_bytes(value, BO, signed=signed)

        if self.data_type == DataType.BITSET:
            return self.bitset_flags(value)

        if self.data_type == DataType.ENUM:
            return self.enum(value)

        if self.data_type == DataType.BOOL:
            return bool(value)

        if self.float_scale is not None:
            return float(value) / self.float_scale

        return value


PREFIX_TO_MODE_MAP = {
    "pb": Mode.POWER_BINS,
    "env": Mode.ENVELOPE,
    "iq": Mode.IQ,
    "sp": Mode.SPARSE,
    "sparse": Mode.SPARSE,
    "peak": None,
    "obst": None,
    "pres": None,
}

# Is tested for completeness
# Order can be important
CONFIG_TO_STRIPPED_REG_NAME_MAP = {
    "mode": None,  # "mode_selection",  # Explicitly set in client
    "profile": "profile_selection",
    "sampling_mode": "sampling_mode",
    "repetition_mode": "repetition_mode",
    "update_rate": "update_rate",
    "sweep_rate": "req_sweep_rate",
    "range_start": "range_start",
    "range_length": "range_length",
    "gain": "gain",
    "downsampling_factor": "downsampling_factor",
    "hw_accelerated_average_samples": "hw_acc_average_samples",
    "bin_count": "req_bin_count",
    "running_average_factor": "run_factor",
    "sweeps_per_frame": "sweeps_per_frame",
    "noise_level_normalization": "noise_level_normalization",
    "maximize_signal_attenuation": "maximize_signal_attenuation",
    "tx_disable": "tx_disable",
    "asynchronous_measurement": "asynchronous_measurement",
    "power_save_mode": "sensor_power_mode",
    "mur": "mur",
    "_depth_lowpass_cutoff_ratio_override": "depth_lpf_ratio_override",
    "_depth_lowpass_cutoff_ratio_value": "depth_lpf_ratio_value",
    "depth_lowpass_cutoff_ratio": None,
    "range_end": None,
    "range_interval": None,
    "sensor": None,
}

STRIPPED_NAME_TO_INFO_REMAP = {
    "output_buffer_length": None,
    "start": "range_start_m",
    "length": "range_length_m",
    "step_length": "step_length_m",
    "step_length": "step_length_m",
    "depth_lpf_ratio_used": "depth_lowpass_cutoff_ratio",
}

ENUM_REMAP = {
    _configs.BaseServiceConfig.RepetitionMode.SENSOR_DRIVEN: "streaming",
    _configs.BaseServiceConfig.RepetitionMode.HOST_DRIVEN: "on_demand",
}

REGISTERS = None


def _match_reg_by_addr(addr, reg):
    return reg.addr == addr


def _match_reg_by_name(name, reg):
    return name in (reg.full_name, reg.stripped_name)


def get_reg(value, mode=None):
    if isinstance(value, Register):
        return value
    elif isinstance(value, int):
        match_fun = partial(_match_reg_by_addr, value)
    elif isinstance(value, str):
        match_fun = partial(_match_reg_by_name, value)
    else:
        raise ValueError

    mode = get_mode(mode)
    matches = []

    for reg in REGISTERS:
        if match_fun(reg):
            if mode is None or reg.modes is None or mode in reg.modes:
                matches.append(reg)

    if len(matches) < 1:
        raise ValueError("unknown reg: {}".format(value))

    if len(matches) > 1:
        raise ValueError("ambiguous reg: {}".format(value))

    return matches[0]


def get_reg_addr(name_or_reg_or_addr, mode=None):
    if isinstance(name_or_reg_or_addr, int):
        addr = name_or_reg_or_addr
        return addr

    name_or_reg = name_or_reg_or_addr
    return get_reg(name_or_reg, mode).addr


def get_regs_for_mode(mode):
    if mode is None:
        raise ValueError

    mode = get_mode(mode)
    return [reg for reg in REGISTERS if reg.modes is None or mode in reg.modes]


def get_regs_for_mode_in_category(category, mode):
    return [reg for reg in get_regs_for_mode(mode) if reg.category == Category(category)]


get_session_info_regs = partial(get_regs_for_mode_in_category, Category.SESSION_INFO)
get_data_info_regs = partial(get_regs_for_mode_in_category, Category.DATA_INFO)


def get_config_key_to_reg_map(mode):  # {config_key: reg}
    mode = get_mode(mode)
    config_cls = _configs.MODE_TO_CONFIG_CLASS_MAP[mode]

    m = {}
    for config_key, reg_name in CONFIG_TO_STRIPPED_REG_NAME_MAP.items():
        if reg_name is None:
            continue

        try:
            param = getattr(config_cls, config_key)
        except AttributeError:
            continue

        if param.is_dummy:
            continue

        m[config_key] = get_reg(reg_name, mode)

    return m


def load_yaml():
    global REGISTERS

    if REGISTERS is not None:
        return

    with importlib.resources.open_text(data, "regmap.yaml") as stream:
        raw_regs = yaml.safe_load(stream)

    REGISTERS = []

    for raw_name, raw_reg in raw_regs.items():
        raw_modes = raw_reg.get("modes", None)
        if raw_modes is None or raw_modes == "None":
            modes = None
        elif isinstance(raw_modes, str):
            try:
                modes = [get_mode(raw_modes)]
            except ValueError:
                continue
        else:  # assumed to be a list
            modes = []
            for m in raw_modes:
                try:
                    modes.append(get_mode(m))
                except ValueError:
                    pass

            if len(modes) == 0:
                continue

        full_name = raw_name.strip().lower()

        try:
            prefix, stripped_name = full_name.split("_", 1)
        except ValueError:
            stripped_name = full_name
        else:
            if prefix in PREFIX_TO_MODE_MAP.keys():
                mode = PREFIX_TO_MODE_MAP[prefix]

                if mode is None:
                    continue

                assert PREFIX_TO_MODE_MAP[prefix] == modes[0] and len(modes) == 1
            else:
                stripped_name = full_name

        addr = raw_reg["address"]
        assert type(addr) == int

        readable, writable = [c in raw_reg.get("access", "rw").strip().lower() for c in "rw"]
        category = Category(raw_reg["category"].strip().lower())
        data_type = DataType(raw_reg["type"].strip().lower())

        reg = Register(
            full_name=full_name,
            stripped_name=stripped_name,
            addr=addr,
            modes=modes,
            readable=readable,
            writable=writable,
            category=category,
            data_type=data_type,
        )

        try:
            reg.float_scale = float(raw_reg["scale"])
        except (KeyError, ValueError):
            pass
        else:
            assert reg.data_type == DataType.INT32

        if data_type == DataType.ENUM:
            enum_values = {str(k).upper(): int(d["value"]) for k, d in raw_reg["values"].items()}
            reg.enum = enum.IntEnum(full_name + "_enum", enum_values)

        if data_type == DataType.BITSET:
            flags = {}
            masks = {}

            for k, v in [(str(k).upper(), int(d["value"])) for k, d in raw_reg["bits"].items()]:
                if v == 0:
                    continue

                if v & (v - 1) == 0:  # is power of 2
                    flags[k] = v
                else:
                    masks[k] = v

            reg.bitset_flags = enum.IntFlag(full_name + "_bitset_flags", flags)
            reg.bitset_masks = enum.IntEnum(full_name + "_bitset_masks", masks)

        REGISTERS.append(reg)


load_yaml()

STATUS_REG = get_reg("status")
STATUS_FLAGS = STATUS_REG.bitset_flags
STATUS_MASKS = STATUS_REG.bitset_masks
