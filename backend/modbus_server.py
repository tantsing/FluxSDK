"""Minimal MODBUS TCP server — exposes sensor data for Artisan connection."""

import struct
import socket
import threading
import time

# Register map (each float32 = 2 registers of 16 bits)
# REG_ADDR | Field         | Type    | Width
# ---------|---------------|---------|------
# 0        | time_sec      | uint32  | 2
# 2        | distance      | uint32  | 2
# 4        | agtron        | float32 | 2
# 6        | roc           | float32 | 2
# 8        | t1            | float32 | 2
# 10       | ror1          | float32 | 2
# 12       | t2            | float32 | 2
# 14       | ror2          | float32 | 2
# 16       | t1_valid      | uint16  | 1
# 17       | t2_valid      | uint16  | 1
# 18       | boom1_count   | uint16  | 1
# 19       | boom2_count   | uint16  | 1
# 20       | packet_count  | uint16  | 1

REG_TOTAL = 21  # 0..20 = 21 registers


def _pack_registers(sensor, packet_count: int) -> dict:
    """Pack current sensor data into MODBUS register dict {addr: word}."""
    regs = {}

    def set_uint32(addr, value):
        b = struct.pack("<I", value)
        regs[addr] = struct.unpack("<H", b[0:2])[0]
        regs[addr + 1] = struct.unpack("<H", b[2:4])[0]

    def set_float32(addr, value):
        b = struct.pack("<f", value)
        regs[addr] = struct.unpack("<H", b[0:2])[0]
        regs[addr + 1] = struct.unpack("<H", b[2:4])[0]

    if sensor is None:
        for i in range(REG_TOTAL):
            regs[i] = 0
        return regs

    set_uint32(0, sensor.time_sec)
    set_uint32(2, sensor.distance)
    set_float32(4, sensor.agtron)
    set_float32(6, sensor.roc)
    set_float32(8, sensor.t1)
    set_float32(10, sensor.ror1)
    set_float32(12, sensor.t2)
    set_float32(14, sensor.ror2)
    regs[16] = sensor.t1_valid
    regs[17] = sensor.t2_valid
    regs[18] = sensor.boom1_count
    regs[19] = sensor.boom2_count
    regs[20] = packet_count

    return regs


def run_modbus_server(store, host: str = "0.0.0.0", port: int = 502):
    """Start a MODBUS TCP server reading data from DataStore."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Try preferred port, fallback to 1502 if permission denied (macOS/Linux)
    actual_port = port
    try:
        sock.bind((host, port))
    except PermissionError:
        if port == 502:
            sock.bind((host, 1502))
            actual_port = 1502
            print(f"[MODBUS] Port 502 requires elevated privileges, using 1502")
        else:
            raise

    sock.listen(1)
    sock.settimeout(1.0)
    print(f"[MODBUS] Listening on {host}:{actual_port}")

    while True:
        try:
            conn, addr = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break

        conn.settimeout(5.0)
        try:
            _handle_client(conn, store)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass


def _handle_client(conn: socket.socket, store):
    """Handle a single MODBUS TCP client connection."""
    while True:
        # Read MBAP header (7 bytes)
        try:
            header = conn.recv(7)
        except socket.timeout:
            break
        if len(header) < 7:
            break

        transaction_id = struct.unpack(">H", header[0:2])[0]
        protocol_id = struct.unpack(">H", header[2:4])[0]
        length = struct.unpack(">H", header[4:6])[0]
        unit_id = header[6]

        # Read remaining data
        remaining = length - 1  # length includes unit_id
        if remaining > 0:
            try:
                data = conn.recv(remaining)
            except socket.timeout:
                break
            if len(data) < remaining:
                break
        else:
            data = b""

        function_code = data[0] if data else 0

        if function_code == 0x03:  # Read Holding Registers
            if len(data) < 5:
                break
            start_addr = struct.unpack(">H", data[1:3])[0]
            quantity = struct.unpack(">H", data[3:5])[0]

            if quantity < 1 or quantity > 125:
                _send_error(conn, transaction_id, unit_id, 0x03, 0x03)
                continue

            if start_addr + quantity > REG_TOTAL:
                _send_error(conn, transaction_id, unit_id, 0x03, 0x02)
                continue

            # Get latest registers
            regs = _pack_registers(store.latest_data, store.packet_count)

            byte_count = quantity * 2
            resp_data = struct.pack(">B", byte_count)
            for i in range(start_addr, start_addr + quantity):
                resp_data += struct.pack(">H", regs.get(i, 0))

            _send_response(conn, transaction_id, unit_id, resp_data)
        else:
            _send_error(conn, transaction_id, unit_id, function_code, 0x01)


def _send_response(conn: socket.socket, transaction_id: int, unit_id: int, data: bytes):
    length = 1 + len(data)  # unit_id + data
    header = struct.pack(">HHH", transaction_id, 0, length)
    conn.sendall(header + bytes([unit_id]) + data)


def _send_error(conn: socket.socket, transaction_id: int, unit_id: int, function_code: int, error_code: int):
    length = 3  # unit_id + error_code
    header = struct.pack(">HHH", transaction_id, 0, length)
    data = bytes([function_code | 0x80, error_code])
    conn.sendall(header + bytes([unit_id]) + data)
