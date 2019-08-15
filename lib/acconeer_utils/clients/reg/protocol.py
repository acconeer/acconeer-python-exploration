from collections import namedtuple
import numpy as np


Reg = namedtuple(
        "Reg",
        [
            "name",
            "mode",
            "addr",
            "rw",
            "type",
            "val_map",
            "info_type",
            "config_attr",
        ],
        )
EncFuns = namedtuple("EncFuns", ["encode_fun", "decode_fun"])
Product = namedtuple("Product", ["name", "id", "baudrate"])

UnpackedRegVal = namedtuple("UnpackedRegVal", ["addr", "val"])
UnpackedRegReadRequest = namedtuple("UnpackedRegReadRequest", ["addr"])
UnpackedRegWriteRequest = namedtuple("UnpackedRegWriteRequest", ["reg_val"])
UnpackedRegReadResponse = namedtuple("UnpackedRegReadResponse", ["reg_val"])
UnpackedRegWriteResponse = namedtuple("UnpackedRegWriteResponse", ["reg_val"])
UnpackedStreamData = namedtuple("UnpackedStreamData", ["result_info", "buffer"])
UnpackedGPIOPin = namedtuple("UnpackedGPIOPin", ["pin"])
UnpackedGPIOPinAndVal = namedtuple("UnpackedGPIOPinAndVal", ["pin", "val"])


class ProtocolError(Exception):
    pass


class PackError(ProtocolError):
    pass


class UnpackError(ProtocolError):
    pass


ADDR_SIZE = 1
REG_SIZE = 4
LEN_FIELD_SIZE = 2
MIN_FRAME_SIZE = 1 + LEN_FIELD_SIZE + 1 + 1
BYTEORDER = "little"
BO = BYTEORDER

MIN_VERSION = 1
DEV_VERSION = 1

START_MARKER = 0xCC
END_MARKER = 0xCD
REG_READ_REQUEST = 0xF8
REG_READ_RESPONSE = 0xF6
REG_WRITE_REQUEST = 0xF9
REG_WRITE_RESPONSE = 0xF5
STREAM_PACKET = 0xFE
GPIO_READ = 0xA0
GPIO_WRITE = 0xA1

STREAM_RESULT_INFO = 0xFD
STREAM_BUFFER = 0xFE

BUF_READ_REQUEST = 0xFA

MAIN_BUFFER_ADDR = 232

STATUS_DATA_READY_MASK = 1 << 0
STATUS_ERROR_MASK = 1 << 2
STATUS_ERROR_ON_SERVICE_CREATION_MASK = 1 << 5

NO_MODE = "none"
MODES = {
    "power_bin": 1,
    "envelope": 2,
    "iq": 3,
    "sparse": 4,
    "distance_peak_fix_threshold": 0x100,
}

FIXED_BUF_SIZE = {
    "power_bin": True,
    "envelope": True,
    "iq": True,
    "distance_peak_fix_threshold": False,
}

BYTE_PER_POINT = {
    "envelope": 2,
    "iq": 4,
    "sparse": 2,
}

PRODUCTS = [
    Product("XM112",  0xACC0, 3000000),
    Product("XM122",  0xACC1, 1000000),
]

float_to_milli_enc_funs = EncFuns(
    lambda v: int(round(v * 1e3)),
    lambda v: v * 1e-3
)

float_to_micro_enc_funs = EncFuns(
    lambda v: int(round(v * 1e6)),
    lambda v: v * 1e-6
)

REGS = [
    Reg(
        "mode_selection",
        NO_MODE,
        2,
        "rw",
        "u",
        MODES,
        None,
        None,
    ),
    Reg(
        "main_control",
        NO_MODE,
        3,
        "w",
        "u",
        {
            "stop": 0,
            "create": 1,
            "activate": 2,
            "create_and_activate": 3,
            "clear_status": 4,
        },
        None,
        None,
    ),
    Reg(
        "streaming_control",
        NO_MODE,
        5,
        "w",
        "u",
        {
            "disable": 0,
            "uart": 1,
        },
        None,
        None,
    ),
    Reg(
        "status",
        NO_MODE,
        6,
        "r",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "uart_baudrate",
        NO_MODE,
        7,
        "rw",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "profile_selection",
        NO_MODE,
        11,
        "w",
        "u",
        None,
        None,
        "session_profile",
    ),
    Reg(
        "product_id",
        NO_MODE,
        16,
        "r",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "product_version",
        NO_MODE,
        17,
        "r",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "range_start",
        NO_MODE,
        32,
        "rw",
        "i",
        float_to_milli_enc_funs,
        None,
        "range_start",
    ),
    Reg(
        "range_length",
        NO_MODE,
        33,
        "rw",
        "i",
        float_to_milli_enc_funs,
        None,
        "range_length",
    ),
    Reg(
        "repetition_mode",
        NO_MODE,
        34,
        "rw",
        "u",
        {
            "fixed": 1,
            "max": 2,
        },
        None,
        None,
    ),
    Reg(
        "frequency",
        NO_MODE,
        35,
        "rw",
        "u",
        float_to_milli_enc_funs,
        "session",
        "sweep_rate",
    ),
    Reg(
        "gain",
        NO_MODE,
        36,
        "rw",
        "u",
        float_to_milli_enc_funs,
        None,
        "gain",
    ),
    Reg(
        "sensor_power_mode",
        NO_MODE,
        37,
        "rw",
        "u",
        {
            "a": 0,
            "b": 1,
            "c": 2,
            "d": 3,
        },
        None,
        None,
    ),
    Reg(
        "stepsize",
        ["iq", "sparse"],
        41,
        "rw",
        "u",
        None,
        None,
        "stepsize",
    ),
    Reg(
        "hw_accelerated_average_samples",
        NO_MODE,
        48,
        "rw",
        "u",
        None,
        None,
        "hw_accelerated_average_samples",
    ),
    Reg(
        "actual_range_start",
        NO_MODE,
        129,
        "r",
        "i",
        float_to_milli_enc_funs,
        "session",
        None,
    ),
    Reg(
        "actual_range_length",
        NO_MODE,
        130,
        "r",
        "i",
        float_to_milli_enc_funs,
        "session",
        None,
    ),
    Reg(
        "actual_stepsize",
        ["iq", "sparse"],
        133,
        "r",
        "i",
        float_to_micro_enc_funs,
        "session",
        None,
    ),
    Reg(
        "output_data_buffer_length",
        NO_MODE,
        233,
        "r",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "data_saturated",
        NO_MODE,
        0x9F,
        "r",
        "b",
        None,
        "sweep",
        None,
    ),
    Reg(
        "sequence_number",
        NO_MODE,
        0xA0,
        "r",
        "u",
        None,
        "sweep",
        None,
    ),

    Reg(
        "requested_bin_count",
        "power_bin",
        64,
        "rw",
        "u",
        None,
        None,
        "bin_count",
    ),
    Reg(
        "actual_bin_count",
        "power_bin",
        131,
        "r",
        "u",
        None,
        "session",
        None,
    ),

    Reg(
        "running_average_factor",
        "envelope",
        64,
        "rw",
        "u",
        float_to_milli_enc_funs,
        None,
        "running_average_factor",
    ),
    Reg(
        "compensate_phase",
        "envelope",
        65,
        "rw",
        "b",
        None,
        None,
        "compensate_phase",
    ),

    Reg(
        "running_average_factor",
        "iq",
        64,
        "rw",
        "u",
        float_to_milli_enc_funs,
        None,
        "running_average_factor",
    ),
    Reg(
        "output_data_compression",
        "iq",
        65,
        "rw",
        "u",
        None,
        None,
        None,
    ),
    Reg(
        "sampling_mode",
        "iq",
        66,
        "rw",
        "u",
        None,
        None,
        "sampling_mode",
    ),
    Reg(
        "number_of_subsweeps",
        "sparse",
        64,
        "rw",
        "u",
        None,
        "session",
        "number_of_subsweeps",
    ),
    Reg(
        "subsweep_rate",
        "sparse",
        65,
        "rw",
        "u",
        float_to_milli_enc_funs,
        None,
        "subsweep_rate",
    ),
    Reg(
        "sparse_sampling_mode",
        "sparse",
        66,
        "rw",
        "u",
        None,
        None,
        "sampling_mode",
    ),
    Reg(
        "data_length",
        "sparse",
        131,
        "r",
        "u",
        None,
        "session",
        None,
    ),
    Reg(
        "actual_subsweep_rate",
        "sparse",
        132,
        "r",
        "u",
        float_to_milli_enc_funs,
        "session",
        None,
    ),

    Reg(
        "peak_count",
        "distance_peak_fix_threshold",
        161,
        "r",
        "u",
        None,
        None,
        None,
    ),

    Reg(
        "data_length",
        ["envelope", "iq"],
        131,
        "r",
        "u",
        None,
        "session",
        None,
    ),
]

MODE_LOOKUP = {v: k for k, v in MODES.items()}
REG_LOOKUP = {k: {} for k in MODES.keys()}
REG_LOOKUP[NO_MODE] = {}
for reg in REGS:
    if isinstance(reg.mode, (list, tuple)):
        modes = reg.mode
    else:
        modes = [reg.mode]

    for mode in modes:
        REG_LOOKUP[mode][reg.name] = reg
        REG_LOOKUP[mode][reg.addr] = reg


def get_mode(mode):
    if isinstance(mode, str):
        return mode
    if mode is None:
        return NO_MODE

    try:
        return MODE_LOOKUP[mode]
    except KeyError:
        raise ProtocolError("unknown mode")


def get_reg(x, mode=None):
    if isinstance(x, Reg):
        return x

    try:
        return REG_LOOKUP[NO_MODE][x]
    except KeyError:
        pass

    mode = get_mode(mode)
    if mode != NO_MODE:
        try:
            return REG_LOOKUP[mode][x]
        except KeyError:
            pass

    raise ProtocolError("unknown register")


def get_addr_for_reg(x, mode=None):
    if isinstance(x, int):
        return x

    return get_reg(x, mode).addr


def encode_reg_val(reg, val, mode=None):
    reg = get_reg(reg, mode)

    if isinstance(reg.val_map, EncFuns):
        x = reg.val_map.encode_fun(val)
    elif isinstance(reg.val_map, dict):
        try:
            x = reg.val_map[val]
        except KeyError:
            raise ProtocolError("could not encode register value (value not in map)")
    else:
        x = val

    if reg.type == "u":
        return x.to_bytes(REG_SIZE, BO)
    elif reg.type == "i":
        return x.to_bytes(REG_SIZE, BO, signed=True)
    elif reg.type == "b":
        return int(x).to_bytes(REG_SIZE, BO)
    else:
        return val


def decode_reg_val(reg, enc_val, mode=None):
    reg = get_reg(reg, mode)

    if reg.type == "u":
        x = int.from_bytes(enc_val, BO)
    elif reg.type == "i":
        x = int.from_bytes(enc_val, BO, signed=True)
    elif reg.type == "b":
        x = any(enc_val)
    else:
        x = enc_val

    if isinstance(reg.val_map, EncFuns):
        return reg.val_map.decode_fun(x)
    elif isinstance(reg.val_map, dict):
        for k, v in reg.val_map.items():
            if v == x:
                return k
        else:
            raise ProtocolError("could not decode register value (value not in map)")
    else:
        return x


def unpack_packet(packet):
    if len(packet) < 1:
        raise UnpackError("package is too short")

    packet_type = packet[0]
    segment = packet[1:]

    if packet_type == REG_READ_RESPONSE:
        return unpack_reg_read_res_segment(segment)
    elif packet_type == REG_WRITE_RESPONSE:
        return unpack_reg_write_res_segment(segment)
    elif packet_type == STREAM_PACKET:
        return unpack_stream_data_segment(segment)
    elif packet_type in [GPIO_READ, GPIO_WRITE]:
        return unpack_gpio_pin_and_val(segment)
    else:
        raise UnpackError("unknown packet type")


def unpack_reg_val(packed):
    if len(packed) != ADDR_SIZE + REG_SIZE:
        raise UnpackError("unexpected package length")

    reg_addr = packed[0]
    enc_val = packed[1:]

    return UnpackedRegVal(reg_addr, enc_val)


def unpack_reg_read_res_segment(segment):
    rv = unpack_reg_val(segment)
    return UnpackedRegReadResponse(rv)


def unpack_reg_write_res_segment(segment):
    rv = unpack_reg_val(segment)
    return UnpackedRegWriteResponse(rv)


def unpack_stream_data_segment(segment):
    result_info = None
    buffer = None
    rest = segment
    while len(rest) > 0:
        if len(rest) < 1 + LEN_FIELD_SIZE:
            raise UnpackError("invalid package length")

        part_type = rest[0]
        data_start_index = 1+LEN_FIELD_SIZE
        part_len = int.from_bytes(rest[1:data_start_index], BO)
        data_end_index = data_start_index + part_len
        part_data = rest[data_start_index:data_end_index]
        rest = rest[data_end_index:]

        if part_type == STREAM_RESULT_INFO:
            s = ADDR_SIZE + REG_SIZE
            if part_len % s != 0:
                raise UnpackError("invalid package length")

            result_info = []
            num_regs = part_len // s
            for i in range(num_regs):
                addr = part_data[s*i]
                enc_val = part_data[s*i+1:s*(i+1)]
                rrv = UnpackedRegVal(addr, enc_val)
                result_info.append(rrv)
        elif part_type == STREAM_BUFFER:
            buffer = part_data
        else:
            raise UnpackError("unknown stream part type")

    return UnpackedStreamData(result_info, buffer)


def unpack_gpio_pin_and_val(segment):
    if len(segment) != 3:
        raise UnpackError("unexpected package length")

    pin, _, val = segment
    return UnpackedGPIOPinAndVal(pin, val)


def pack_reg_val(reg_val):
    if len(reg_val.val) != REG_SIZE:
        raise PackError("register value must be {} bytes".format(REG_SIZE))
    packed = bytearray()
    packed.extend(reg_val.addr.to_bytes(ADDR_SIZE, BO))
    packed.extend(reg_val.val)
    return packed


def pack_packet(packet):
    if isinstance(packet, UnpackedRegReadRequest):
        packet_type = REG_READ_REQUEST
        packet_data = bytearray()
        packet_data.extend(packet.addr.to_bytes(ADDR_SIZE, BO))
    elif isinstance(packet, UnpackedRegWriteRequest):
        packet_type = REG_WRITE_REQUEST
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, UnpackedRegReadResponse):
        packet_type = REG_READ_RESPONSE
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, UnpackedRegWriteResponse):
        packet_type = REG_WRITE_RESPONSE
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, UnpackedGPIOPin):
        packet_type = GPIO_READ
        packet_data = bytearray([packet.pin])
    elif isinstance(packet, UnpackedGPIOPinAndVal):
        packet_type = GPIO_WRITE
        packet_data = bytearray([packet.pin, packet.val])
    else:
        raise TypeError("unknown type of packet")

    packet_bytes = bytearray()
    packet_bytes.append(packet_type)
    packet_bytes.extend(packet_data)
    return packet_bytes


def extract_packet_from_frame(frame):
    if len(frame) < MIN_FRAME_SIZE:
        raise ProtocolError("invalid frame (frame too short)")
    if frame[0] != START_MARKER:
        raise ProtocolError("invalid frame (incorrect start marker)")
    if frame[-1] != END_MARKER:
        raise ProtocolError("invalid frame (incorrect start marker)")

    packet_len = int.from_bytes(frame[1:1+LEN_FIELD_SIZE], BO)
    packet = frame[1+LEN_FIELD_SIZE:-1]

    if len(packet) - 1 != packet_len:
        raise ProtocolError("invalid frame (packet length mismatch)")

    return packet


def insert_packet_into_frame(packet):
    if not isinstance(packet, bytearray):
        packet = pack_packet(packet)

    packet_len = len(packet) - 1
    frame = bytearray()
    frame.append(START_MARKER)
    frame.extend(packet_len.to_bytes(LEN_FIELD_SIZE, BO))
    frame.extend(packet)
    frame.append(END_MARKER)
    return frame


def decode_output_buffer(buffer, mode, number_of_subsweeps=None):
    mode = get_mode(mode)
    if mode == "power_bin":
        return np.frombuffer(buffer, dtype="<f4").astype("float")
    elif mode == "envelope":
        return np.frombuffer(buffer, dtype="<u2").astype("float")
    elif mode == "iq":
        sweep = np.frombuffer(buffer, dtype="<i2").astype("float") * 2**(-12)
        return sweep.reshape((2, -1), order="F").view(dtype="complex").reshape(-1)
    elif mode == "sparse":
        sweep = np.frombuffer(buffer, dtype="<u2").astype("float")
        sweep -= 2**15
        sweep = sweep.reshape((number_of_subsweeps, -1))
        return sweep
    elif mode == "distance_peak_fix_threshold":
        sweep = np.frombuffer(buffer, dtype="<f4, <u2")
        return sweep.astype("float, float").view("float").reshape((-1, 2))
    else:
        raise NotImplementedError
