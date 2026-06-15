import asyncio
import logging
import os
import sys
from backend.models import SensorData, StatusResponse
from backend.bluetooth import BluetoothDebugger
from backend.parser import OmniFluxDataParser

logger = logging.getLogger(__name__)


class DataStore:
    """全局状态管理，桥接蓝牙层和 Web 层"""

    def __init__(self):
        self.debugger = BluetoothDebugger()
        self.parser = OmniFluxDataParser()

        self._selected_fields: set[str] = set()
        self._output_enabled = True
        self._packet_count = 0
        self._latest_data: SensorData | None = None

        self.debugger.on_data_received = self._on_bluetooth_data
        self.debugger.on_disconnected = self._on_device_disconnected

        # WebSocket 订阅者
        self._subscribers: list[asyncio.Queue] = []

        # 数据文件路径（与 flux.txt 中的逻辑一致）
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self._data_file = os.path.join(base_dir, "omniflux_latest.txt")
        self._init_data_file()

    def _on_device_disconnected(self):
        """设备异常断开时通知所有前端"""
        print("[BLE] 设备已断开", flush=True)
        for q in self._subscribers:
            try:
                q.put_nowait({"type": "disconnected"})
            except asyncio.QueueFull:
                pass

    def _init_data_file(self):
        """确保数据文件存在，如不存在则创建并写入默认值（与 flux.txt 逻辑一致）"""
        if not os.path.exists(self._data_file):
            try:
                with open(self._data_file, 'w') as f:
                    f.write("0,0,0,0,0,0,0,0,0,0,0,0")
                print(f"[FILE] 已创建数据文件: {self._data_file}", flush=True)
            except Exception as e:
                print(f"[FILE] 创建文件失败: {e}", flush=True)

    def _save_to_file(self, sensor: SensorData):
        """将最新传感器数据写入 omniflux_latest.txt，按选中字段过滤"""
        all_fields = ["time_sec","distance","agtron","roc","t1","ror1","t2","ror2",
                      "t1_valid","t2_valid","boom1_count","boom2_count"]
        float_fields = {"agtron","roc","t1","ror1","t2","ror2"}
        try:
            if self._selected_fields:
                fields = [f for f in all_fields if f in self._selected_fields]
            else:
                fields = all_fields
            values = []
            for f in fields:
                v = getattr(sensor, f)
                if f in float_fields:
                    values.append(f"{v:.1f}")
                else:
                    values.append(str(v))
            with open(self._data_file, 'w') as f:
                f.write(",".join(values))
        except Exception:
            pass

    @property
    def data_file(self) -> str:
        return self._data_file

    def _on_bluetooth_data(self, data: bytes):
        hex_str = data.hex(' ')
        print(f"\n[RAW] len={len(data)} | {hex_str}", flush=True)

        sensor = self.parser.parse_response(data)
        if sensor is None:
            print("[PARSER] SKIP (no Cmd 6 frame found)", flush=True)
            return

        print(f"[PARSED] t={sensor.time_sec}s dist={sensor.distance}mm "
              f"agtron={sensor.agtron:.1f} roc={sensor.roc:.1f} "
              f"t1={sensor.t1:.1f}℃ ror1={sensor.ror1:.2f} "
              f"t2={sensor.t2:.1f}℃ ror2={sensor.ror2:.2f} "
              f"t1v={sensor.t1_valid} t2v={sensor.t2_valid} "
              f"b1={sensor.boom1_count} b2={sensor.boom2_count}", flush=True)

        self._packet_count += 1
        self._latest_data = sensor
        self._save_to_file(sensor)

        # 广播给所有 WebSocket 订阅者
        payload = sensor.model_dump()
        payload["_packet_count"] = self._packet_count
        for q in self._subscribers:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    @property
    def is_connected(self) -> bool:
        return self.debugger.is_connected

    @property
    def scanning(self) -> bool:
        return getattr(self, '_scanning', False)

    @scanning.setter
    def scanning(self, v: bool):
        self._scanning = v

    @property
    def packet_count(self) -> int:
        return self._packet_count

    @property
    def latest_data(self) -> SensorData | None:
        return self._latest_data

    @property
    def selected_fields(self) -> set[str]:
        return self._selected_fields

    @selected_fields.setter
    def selected_fields(self, fields: set[str]):
        self._selected_fields = fields

    @property
    def output_enabled(self) -> bool:
        return self._output_enabled

    @output_enabled.setter
    def output_enabled(self, v: bool):
        self._output_enabled = v

    def get_status(self) -> StatusResponse:
        return StatusResponse(
            connected=self.is_connected,
            device_name=self.debugger.device_name,
            device_address=self.debugger.device_address,
            packet_count=self._packet_count,
            scanning=self.scanning,
        )
