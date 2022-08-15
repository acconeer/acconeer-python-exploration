# Copyright (c) Acconeer AB, 2022
# All rights reserved

"""
This file handles the lower layer of the UART protocol.
"""
import logging
import queue
import threading
from enum import Enum


_LOG = logging.getLogger(__name__)


class Packet:
    """
    Base class for all packages transmitted over UART protocol.
    """

    PROTOCOL_START_MARKER = 0xCC
    PROTOCOL_END_MARKER = 0xCD

    def __init__(self, payload):
        self.payload = payload

    @property
    def packet_type(self):
        raise NotImplementedError

    def get_byte_array(self):
        """
        Packet the data for this packet into a bytearray()
        that can be transmitted over UART.
        """
        data = bytearray([])
        data.append(Packet.PROTOCOL_START_MARKER)
        packet_length = int(len(self.payload))
        data.extend(packet_length.to_bytes(2, byteorder="little"))
        data.append(self.packet_type)
        data.extend(self.payload)
        data.append(Packet.PROTOCOL_END_MARKER)
        return data


class UartReader(threading.Thread):
    """Class that reads packets from the serial port"""

    HEADER_LENGTH = 3  # Excluding start marker
    PACKET_TIMEOUT = 0.5
    DEFAULT_READ_TIMEOUT = 10
    DEFAULT_READ_STREAM_TIMEOUT = 2
    packet_count = 0

    def __init__(self, ser, response_classes):
        """
        Create a reader that reads packages from the UART.

        ser: The serial port object to read from
        packet_types: An array with response package classes
        """
        threading.Thread.__init__(self, name="UartReader")
        self._ser = ser
        self._stop_event = threading.Event()
        self.daemon = True
        self._packets = dict()
        self._packet_types = dict()
        # Create a map with key=packet_type, value=packet class
        # also create a queue for each possible packet type
        for response_class in response_classes:
            if response_class.packet_type in self._packet_types:
                raise ValueError(f"Duplicate package type specified: {response_class.packet_type}")
            if not isinstance(response_class.packet_type, int):
                raise ValueError(
                    f"packet_type must be an int: {response_class}: {response_class.packet_type}"
                )
            self._packet_types[response_class.packet_type] = response_class
            self._packets[response_class.packet_type] = queue.Queue()

    def stop(self):
        self._stop_event.set()
        self._ser.cancel_read()
        self.join()

    def _wait_for_start_marker(self):
        self._ser.timeout = None
        errors = 0
        while not self._stop_event.is_set():
            data = self._ser.read(1)
            if len(data) != 1:
                continue

            if data[0] != Packet.PROTOCOL_START_MARKER:
                if errors == 0:
                    # Invalid start marker before first packet is not an error
                    # but rather some data that was around from previous session
                    _LOG.log(
                        logging.WARNING if self.packet_count == 0 else logging.ERROR,
                        "Invalid start marker %d",
                        data[0],
                    )
                errors += 1
            else:
                break

        if errors != 0:
            _LOG.log(
                logging.WARNING if self.packet_count == 0 else logging.ERROR,
                "Got %d invalid start markers",
                errors,
            )

        self.packet_count += 1

    def _read_packet_header(self):
        _LOG.debug("Reading packet header")
        self._ser.timeout = UartReader.PACKET_TIMEOUT

        header = self._ser.read(UartReader.HEADER_LENGTH)
        if self._stop_event.is_set():
            return (None, None)

        if len(header) != UartReader.HEADER_LENGTH:
            _LOG.error("Invalid header length %d", len(header))
            return (None, None)

        _LOG.debug("Got packet header %s", header)

        payload_length = header[0] | header[1] << 8
        packet_type = header[2]
        if packet_type not in self._packet_types:
            _LOG.error("Unknown packet type 0x%02X", packet_type)
            return (None, None)

        return (payload_length, packet_type)

    def _read_payload_and_end_marker(self, payload_length):
        _LOG.debug("Reading payload and end marker len=%d", payload_length)
        self._ser.timeout = (
            UartReader.PACKET_TIMEOUT + (payload_length + 1) / self._ser.baudrate * 10
        )
        payload = self._ser.read(payload_length + 1)
        if payload and len(payload) == (payload_length + 1):
            return (payload[:payload_length], payload[payload_length])
        _LOG.debug("wrong payload length %d was %s", len(payload), payload)
        return (None, None)

    def run(self):
        _LOG.debug("UartReader starting")
        try:
            while not self._stop_event.is_set():
                self._wait_for_start_marker()
                if self._stop_event.is_set():
                    break

                (payload_length, packet_type) = self._read_packet_header()
                if self._stop_event.is_set():
                    break

                if not payload_length:
                    continue

                (payload, end_marker) = self._read_payload_and_end_marker(payload_length)

                if self._stop_event.is_set():
                    break

                if not payload:
                    _LOG.error("Protocol out of sync, starting over (payload)")
                    continue
                if end_marker != Packet.PROTOCOL_END_MARKER:
                    _LOG.error("Invalid end marker: %s", end_marker)
                    continue

                _LOG.debug(
                    "Got packet type=%s payload[:10]=%s end_marker=%s",
                    packet_type,
                    payload[:10],
                    end_marker,
                )
                packet = self._packet_types[packet_type](payload)
                self._packets[packet_type].put(packet)
        except Exception as exception:
            _LOG.error("UartReader: Got exception %s", exception)
            raise exception
        finally:
            _LOG.debug("UartReader stopping")

    def have_packet(self, packet_type):
        key = packet_type.value if isinstance(packet_type, Enum) else packet_type
        return not self._packets[key].empty()

    def wait_packet(self, packet_type, timeout):
        _LOG.debug("Waiting for packet of type %s with a timeout of %.2f", packet_type, timeout)
        key = packet_type.value if isinstance(packet_type, Enum) else packet_type
        packet = self._packets[key].get(timeout=timeout)
        packet_type_value = packet_type.value if isinstance(packet_type, Enum) else packet_type
        _LOG.debug("Got packet of type %s (0x%02X)", packet_type, packet_type_value)
        return packet
