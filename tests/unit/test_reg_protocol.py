import acconeer.exptool.a111._clients.reg.protocol as ptcl
from acconeer.exptool.a111 import Mode
from acconeer.exptool.a111._clients.reg import regmap


unp_reg_val = ptcl.RegVal(2, b"\x03\x00\x00\x00")
unp_reg_read_res = ptcl.RegReadResponse(unp_reg_val)
pkd_reg_read_res_segment = b"\x02\x03\x00\x00\x00"
pkd_reg_read_res_packet = bytearray([ptcl.REG_READ_RESPONSE]) + pkd_reg_read_res_segment
pkd_reg_read_res_frame = (
    bytearray([ptcl.START_MARKER])
    + b"\x05\x00"
    + pkd_reg_read_res_packet
    + bytearray([ptcl.END_MARKER])
)

unp_reg_write_req = ptcl.RegWriteRequest(unp_reg_val)
pkd_reg_write_req_packet = bytearray()
pkd_reg_write_req_packet.append(ptcl.REG_WRITE_REQUEST)
pkd_reg_write_req_packet.append(unp_reg_write_req.reg_val.addr)
pkd_reg_write_req_packet.extend(unp_reg_write_req.reg_val.val)
pkd_reg_write_req_frame = bytearray()
pkd_reg_write_req_frame.append(ptcl.START_MARKER)
pkd_reg_write_req_frame.extend(b"\x05\x00")  # len
pkd_reg_write_req_frame.extend(pkd_reg_write_req_packet)
pkd_reg_write_req_frame.append(ptcl.END_MARKER)


def test_unpack_packet():
    unpacked = ptcl.unpack_packet(pkd_reg_read_res_packet)
    assert unpacked == unp_reg_read_res


def test_unpack_reg_read_res_segment():
    unpacked = ptcl.unpack_reg_read_res_segment(pkd_reg_read_res_segment)
    assert unpacked == unp_reg_read_res


def test_unpack_stream_data_segment():
    reg = regmap.get_reg("run_factor", Mode.ENVELOPE)
    rv_addr = reg.addr
    rv_enc_val = reg.encode(123)
    rvs = [ptcl.RegVal(rv_addr, rv_enc_val)]
    buffer = bytearray(b"\x12\x34\x56")
    unp_stream_data = ptcl.StreamData(rvs, buffer)

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
