"""Minimal MODBUS TCP server — exposes sensor data for Artisan connection."""

import struct
import socket
import threading
import time

# Register map — single int16 registers with ×10 scaling for decimals
# Designed for Artisan: set div=10 on temperature/probe inputs
#
# REG | Field        | Scale | Artisan div | Notes
# ----|--------------|-------|-------------|------------------
# 0   | agtron       | ×10   | 10          | Color value
# 1   | roc          | ×10   | 10          | RoC Agtron/min
# 2   | distance     | ×1    | 1           | TOF mm
# 3   | t1           | ×10   | 10          | Probe TC1 (°C)
# 4   | ror1         | ×10   | 10          | TC1 RoR (°C/min)
# 5   | t2           | ×10   | 10          | Probe TC2 (°C)
# 6   | ror2         | ×10   | 10          | TC2 RoR (°C/min)
# 7   | boom1_count  | ×1    | 1           | First crack
# 8   | boom2_count  | ×1    | 1           | Second crack
# 9   | time_sec     | ×1    | 1           | Time (low 16 bits)
# 10  | t1_valid     | ×1    | 1           | 0/1
# 11  | t2_valid     | ×1    | 1           | 0/1
# 12  | packet_count | ×1    | 1           | Total packets

REG_TOTAL = 13


def _clamp_i16(v: int) -> int:
    """Clamp to signed 16-bit range."""
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


def _pack_registers(sensor, packet_count: int) -> dict:
    """Pack sensor data into single int16 registers with ×10 scaling."""
    regs = {}
    if sensor is None:
        for i in range(REG_TOTAL):
            regs[i] = 0
        return regs

    regs[0] = _clamp_i16(int(sensor.agtron * 10))
    regs[1] = _clamp_i16(int(sensor.roc * 10))
    regs[2] = _clamp_i16(sensor.distance)
    regs[3] = _clamp_i16(int(sensor.t1 * 10))
    regs[4] = _clamp_i16(int(sensor.ror1 * 10))
    regs[5] = _clamp_i16(int(sensor.t2 * 10))
    regs[6] = _clamp_i16(int(sensor.ror2 * 10))
    regs[7] = _clamp_i16(sensor.boom1_count)
    regs[8] = _clamp_i16(sensor.boom2_count)
    regs[9] = sensor.time_sec & 0xFFFF
    regs[10] = sensor.t1_valid
    regs[11] = sensor.t2_valid
    regs[12] = packet_count & 0xFFFF

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
            resp_data = bytes([0x03, byte_count])
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
