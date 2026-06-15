"""MODBUS TCP server for OmniFlux — exposes sensor data for Artisan."""

import struct
import socket
import os
import sys

# Resolve data file path
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(_BASE, "omniflux_latest.txt")

# Register map (single int16, scaled x10 for decimals)
# 0=agtron, 1=roc, 2=distance, 3=t1, 4=ror1, 5=t2, 6=ror2
# 7=boom1, 8=boom2, 9=time_sec, 10=t1v, 11=t2v, 12=pkt
REG_TOTAL = 13


def i16(v):
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


def read_regs():
    r = {}
    for i in range(REG_TOTAL):
        r[i] = 0
    try:
        with open(DATA_FILE, "r") as f:
            p = f.read().strip().split(",")
        if len(p) >= 12:
            r[0] = i16(int(float(p[2]) * 10))
            r[1] = i16(int(float(p[3]) * 10))
            r[2] = i16(int(float(p[1])))
            r[3] = i16(int(float(p[4]) * 10))
            r[4] = i16(int(float(p[5]) * 10))
            r[5] = i16(int(float(p[6]) * 10))
            r[6] = i16(int(float(p[7]) * 10))
            r[7] = i16(int(float(p[10])))
            r[8] = i16(int(float(p[11])))
            r[9] = int(float(p[0])) & 0xFFFF
            r[10] = int(float(p[8]))
            r[11] = int(float(p[9]))
            r[12] = 0
    except Exception:
        pass
    return r


def run_modbus_server(host="0.0.0.0", port=1502):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, port))
    s.listen(1)
    s.settimeout(1.0)
    print("[MODBUS] port %s" % port)

    while True:
        try:
            c, a = s.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        c.settimeout(5.0)
        try:
            _serve(c)
        except Exception:
            pass
        try:
            c.close()
        except Exception:
            pass


def _serve(c):
    while True:
        try:
            h = c.recv(7)
        except socket.timeout:
            break
        if len(h) < 7:
            break
        tid = struct.unpack(">H", h[0:2])[0]
        length = struct.unpack(">H", h[4:6])[0]
        uid = h[6]
        n = length - 1
        if n > 0:
            try:
                d = c.recv(n)
            except socket.timeout:
                break
            if len(d) < n:
                break
        else:
            d = b""
        fc = d[0] if d else 0
        if fc == 0x03 and len(d) >= 5:
            sa = struct.unpack(">H", d[1:3])[0]
            qty = struct.unpack(">H", d[3:5])[0]
            if qty < 1 or qty > 125:
                _err(c, tid, uid, 0x03, 0x03)
                continue
            if sa + qty > REG_TOTAL:
                _err(c, tid, uid, 0x03, 0x02)
                continue
            regs = read_regs()
            bc = qty * 2
            resp = bytes([0x03, bc])
            for i in range(sa, sa + qty):
                resp += struct.pack(">H", regs.get(i, 0))
            _ok(c, tid, uid, resp)
        else:
            _err(c, tid, uid, fc, 0x01)


def _ok(c, tid, uid, data):
    length = 1 + len(data)
    c.sendall(struct.pack(">HHH", tid, 0, length) + bytes([uid]) + data)


def _err(c, tid, uid, fc, ec):
    length = 3
    c.sendall(struct.pack(">HHH", tid, 0, length) + bytes([uid, fc | 0x80, ec]))
