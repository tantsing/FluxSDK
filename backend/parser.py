import struct
from typing import Optional
from backend.models import SensorData


SYNC = b'\xDF\xDF'
FRAME_MIN_LEN = 6  # sync(2) + func(1) + cmd(1) + len(1) + checksum(1)
REALTIME_STRUCT_LEN = 38  # sdk_det_roast_realtime_t


class OmniFluxDataParser:
    """DF DF 帧协议解析器"""

    @staticmethod
    def find_frames(data: bytes) -> list[tuple[int, int, int, bytes]]:
        """Find all complete protocol frames in data.
        Returns list of (func, cmd, payload_len, payload_bytes).
        """
        frames = []
        i = 0
        while i <= len(data) - FRAME_MIN_LEN:
            if data[i:i+2] != SYNC:
                i += 1
                continue

            func = data[i+2]
            cmd = data[i+3]
            plen = data[i+4]

            frame_end = i + 5 + plen + 1  # header(5) + payload + checksum(1)
            if frame_end > len(data):
                i += 1
                continue

            payload = data[i+5:i+5+plen]
            frames.append((func, cmd, plen, payload))
            i = frame_end
        return frames

    @staticmethod
    def parse_realtime(payload: bytes) -> Optional[SensorData]:
        """Parse 38-byte sdk_det_roast_realtime_t payload."""
        if len(payload) < REALTIME_STRUCT_LEN:
            return None

        try:
            sensor = SensorData()
            offset = 0

            sensor.time_sec = struct.unpack('<I', payload[offset:offset+4])[0]
            offset += 4

            sensor.distance = struct.unpack('<I', payload[offset:offset+4])[0]
            offset += 4

            sensor.agtron = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.roc = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.t1 = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.ror1 = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.t2 = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.ror2 = struct.unpack('<f', payload[offset:offset+4])[0]
            offset += 4

            sensor.t1_valid = payload[offset]
            offset += 1

            sensor.t2_valid = payload[offset]
            offset += 1

            sensor.boom1_count = struct.unpack('<H', payload[offset:offset+2])[0]
            offset += 2

            sensor.boom2_count = struct.unpack('<H', payload[offset:offset+2])[0]

            return sensor
        except Exception:
            return None

    @staticmethod
    def parse_response(data: bytes) -> Optional[SensorData]:
        """Parse incoming notification data, extracting Cmd 6 realtime frames."""
        for func, cmd, plen, payload in OmniFluxDataParser.find_frames(data):
            if func == 0x03 and cmd == 0x06 and plen >= REALTIME_STRUCT_LEN:
                return OmniFluxDataParser.parse_realtime(payload)
        return None
