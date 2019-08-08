import pytest

import acconeer_utils.clients.reg.protocol as ptcl


test_mode = "envelope"
test_mode_val = 2
test_reg = ptcl.REG_LOOKUP[ptcl.NO_MODE]["main_control"]
test_mode_reg = ptcl.REG_LOOKUP["envelope"]["running_average_factor"]

unp_reg_val = ptcl.UnpackedRegVal(2, b"\x03\x00\x00\x00")
unp_reg_read_res = ptcl.UnpackedRegReadResponse(unp_reg_val)
pkd_reg_read_res_segment = b"\x02\x03\x00\x00\x00"
pkd_reg_read_res_packet = bytearray([ptcl.REG_READ_RESPONSE]) + pkd_reg_read_res_segment
pkd_reg_read_res_frame = (bytearray([ptcl.START_MARKER])
                          + b"\x05\x00"
                          + pkd_reg_read_res_packet
                          + bytearray([ptcl.END_MARKER]))

unp_reg_write_req = ptcl.UnpackedRegWriteRequest(unp_reg_val)
pkd_reg_write_req_packet = bytearray()
pkd_reg_write_req_packet.append(ptcl.REG_WRITE_REQUEST)
pkd_reg_write_req_packet.append(unp_reg_write_req.reg_val.addr)
pkd_reg_write_req_packet.extend(unp_reg_write_req.reg_val.val)
pkd_reg_write_req_frame = bytearray()
pkd_reg_write_req_frame.append(ptcl.START_MARKER)
pkd_reg_write_req_frame.extend(b"\x05\x00")  # len
pkd_reg_write_req_frame.extend(pkd_reg_write_req_packet)
pkd_reg_write_req_frame.append(ptcl.END_MARKER)


def test_get_mode():
    assert ptcl.get_mode(test_mode) == test_mode
    assert ptcl.get_mode(test_mode_val) == test_mode
    assert ptcl.get_mode(None) is ptcl.NO_MODE

    with pytest.raises(ptcl.ProtocolError):
        ptcl.get_mode(2**17)


def test_get_reg():
    assert ptcl.get_reg(test_reg.name) == test_reg
    assert ptcl.get_reg(test_reg.name, test_mode) == test_reg
    assert ptcl.get_reg(test_reg.name, test_mode_val) == test_reg
    assert ptcl.get_reg(test_mode_reg.name, test_mode) == test_mode_reg
    assert ptcl.get_reg(test_mode_reg.name, test_mode_val) == test_mode_reg
    assert ptcl.get_reg(test_reg) == test_reg
    assert ptcl.get_reg(test_reg.addr) == test_reg

    with pytest.raises(ptcl.ProtocolError):
        ptcl.get_reg(test_mode_reg.name)


def test_get_addr_for_reg():
    assert ptcl.get_addr_for_reg(test_reg) == test_reg.addr
    assert ptcl.get_addr_for_reg(123) == 123


def test_encode_reg_val():
    assert ptcl.encode_reg_val("mode_selection", "envelope") == b"\x02\x00\x00\x00"
    assert ptcl.encode_reg_val("range_start", 0.06) == b"\x3c\x00\x00\x00"


def test_decode_reg_val():
    assert ptcl.decode_reg_val("mode_selection", b"\x02\x00\x00\x00") == "envelope"
    assert ptcl.decode_reg_val("range_start", b"\x3c\x00\x00\x00") == 0.06


def test_unpack_packet():
    unpacked = ptcl.unpack_packet(pkd_reg_read_res_packet)
    assert unpacked == unp_reg_read_res


def test_unpack_reg_read_res_segment():
    unpacked = ptcl.unpack_reg_read_res_segment(pkd_reg_read_res_segment)
    assert unpacked == unp_reg_read_res


def test_unpack_stream_data_segment():
    rv_addr = ptcl.get_addr_for_reg(test_mode_reg)
    rv_enc_val = ptcl.encode_reg_val(test_mode_reg, 123)
    rvs = [ptcl.UnpackedRegVal(rv_addr, rv_enc_val)]
    buffer = bytearray(b'\x12\x34\x56')
    unp_stream_data = ptcl.UnpackedStreamData(rvs, buffer)

    pkd_stream_data_segment = bytearray()
    pkd_stream_data_segment.append(ptcl.STREAM_BUFFER)
    pkd_stream_data_segment.extend(b"\x03\x00")
    pkd_stream_data_segment.extend(buffer)
    pkd_stream_data_segment.append(ptcl.STREAM_RESULT_INFO)
    pkd_stream_data_segment.extend(b"\x05\x00")
    pkd_stream_data_segment.append(rv_addr)
    pkd_stream_data_segment.extend(rv_enc_val)

    unpacked = ptcl.unpack_stream_data_segment(pkd_stream_data_segment)
    assert unpacked == unp_stream_data


def test_pack_packet():
    packed = ptcl.pack_packet(unp_reg_write_req)
    assert packed == pkd_reg_write_req_packet


def test_extract_packet_from_frame():
    packet = ptcl.extract_packet_from_frame(pkd_reg_read_res_frame)
    assert packet == pkd_reg_read_res_packet


def test_insert_packet_into_frame():
    frame = ptcl.insert_packet_into_frame(unp_reg_write_req)
    assert frame == pkd_reg_write_req_frame
