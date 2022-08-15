# Copyright (c) Acconeer AB, 2022
# All rights reserved

from collections import namedtuple

import numpy as np

from acconeer.exptool.a111._modes import Mode, get_mode


RegVal = namedtuple("RegVal", ["addr", "val"])
RegReadRequest = namedtuple("RegReadRequest", ["addr"])
RegWriteRequest = namedtuple("RegWriteRequest", ["reg_val"])
RegReadResponse = namedtuple("RegReadResponse", ["reg_val"])
RegWriteResponse = namedtuple("RegWriteResponse", ["reg_val"])
BufferReadRequest = namedtuple("BufferReadRequest", ["addr"])
BufferReadResponse = namedtuple("BufferReadResponse", ["addr", "buffer"])
StreamData = namedtuple("StreamData", ["result_info", "buffer"])


class ProtocolError(Exception):
    pass


ADDR_SIZE = 1
REG_SIZE = 4
LEN_FIELD_SIZE = 2
MIN_FRAME_SIZE = 1 + LEN_FIELD_SIZE + 1 + 1
BYTEORDER = "little"
BO = BYTEORDER

START_MARKER = 0xCC
END_MARKER = 0xCD
REG_READ_REQUEST = 0xF8
REG_READ_RESPONSE = 0xF6
REG_WRITE_REQUEST = 0xF9
REG_WRITE_RESPONSE = 0xF5
STREAM_PACKET = 0xFE
BUF_READ_REQUEST = 0xFA
BUF_READ_RESPONSE = 0xF7
STREAM_RESULT_INFO = 0xFD
STREAM_BUFFER = 0xFE

MAIN_BUFFER_ADDR = 0xE8


def unpack_packet(packet):
    if len(packet) < 1:
        raise ProtocolError("package is too short")

    packet_type = packet[0]
    segment = packet[1:]

    if packet_type == REG_READ_RESPONSE:
        return unpack_reg_read_res_segment(segment)
    elif packet_type == REG_WRITE_RESPONSE:
        return unpack_reg_write_res_segment(segment)
    elif packet_type == BUF_READ_RESPONSE:
        return unpack_buf_read_res_segment(segment)
    elif packet_type == STREAM_PACKET:
        return unpack_stream_data_segment(segment)
    else:
        raise ProtocolError("unknown packet type")


def unpack_reg_val(packed):
    if len(packed) != ADDR_SIZE + REG_SIZE:
        raise ProtocolError("unexpected package length")

    reg_addr = packed[0]
    enc_val = packed[1:]

    return RegVal(reg_addr, enc_val)


def unpack_reg_read_res_segment(segment):
    rv = unpack_reg_val(segment)
    return RegReadResponse(rv)


def unpack_reg_write_res_segment(segment):
    rv = unpack_reg_val(segment)
    return RegWriteResponse(rv)


def unpack_buf_read_res_segment(segment):
    buf_addr = segment[0]
    buffer = segment[1:]
    return BufferReadResponse(buf_addr, buffer)


def unpack_stream_data_segment(segment):
    result_info = None
    buffer = None
    rest = segment
    while len(rest) > 0:
        if len(rest) < 1 + LEN_FIELD_SIZE:
            raise ProtocolError("invalid package length")

        part_type = rest[0]
        data_start_index = 1 + LEN_FIELD_SIZE
        part_len = int.from_bytes(rest[1:data_start_index], BO)
        data_end_index = data_start_index + part_len
        part_data = rest[data_start_index:data_end_index]
        rest = rest[data_end_index:]

        if part_type == STREAM_RESULT_INFO:
            s = ADDR_SIZE + REG_SIZE
            if part_len % s != 0:
                raise ProtocolError("invalid package length")

            result_info = []
            num_regs = part_len // s
            for i in range(num_regs):
                addr = part_data[s * i]
                enc_val = part_data[s * i + 1 : s * (i + 1)]
                rrv = RegVal(addr, enc_val)
                result_info.append(rrv)
        elif part_type == STREAM_BUFFER:
            buffer = part_data
        else:
            raise ProtocolError("unknown stream part type")

    return StreamData(result_info, buffer)


def pack_reg_val(reg_val):
    if len(reg_val.val) != REG_SIZE:
        raise ProtocolError("register value must be {} bytes".format(REG_SIZE))
    packed = bytearray()
    packed.extend(reg_val.addr.to_bytes(ADDR_SIZE, BO))
    packed.extend(reg_val.val)
    return packed


def pack_packet(packet):
    if isinstance(packet, RegReadRequest):
        packet_type = REG_READ_REQUEST
        packet_data = bytearray()
        packet_data.extend(packet.addr.to_bytes(ADDR_SIZE, BO))
    elif isinstance(packet, RegWriteRequest):
        packet_type = REG_WRITE_REQUEST
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, RegReadResponse):
        packet_type = REG_READ_RESPONSE
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, RegWriteResponse):
        packet_type = REG_WRITE_RESPONSE
        packet_data = pack_reg_val(packet.reg_val)
    elif isinstance(packet, BufferReadRequest):
        packet_type = BUF_READ_REQUEST
        packet_data = bytearray()
        packet_data.extend(packet.addr.to_bytes(ADDR_SIZE, BO))
        packet_data.extend([0, 0])
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

    packet_len = int.from_bytes(frame[1 : 1 + LEN_FIELD_SIZE], BO)
    packet = frame[1 + LEN_FIELD_SIZE : -1]

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


def decode_output_buffer(buffer, mode, sweeps_per_frame=None):
    mode = get_mode(mode)

    if mode == Mode.POWER_BINS:
        return np.frombuffer(buffer, dtype="<u2").astype("float")
    elif mode == Mode.ENVELOPE:
        return np.frombuffer(buffer, dtype="<u2").astype("float")
    elif mode == Mode.IQ:
        data = np.frombuffer(buffer, dtype="<i2").astype("float")
        return data.reshape((-1, 2)).view(dtype="complex").flatten()
    elif mode == Mode.SPARSE:
        data = np.frombuffer(buffer, dtype="<u2").astype("float")
        data = data.reshape((sweeps_per_frame, -1))
        return data
    else:
        raise NotImplementedError
