import asyncio
import threading
import time
import queue
from typing import Optional, List


class BluetoothDebugger:
    CHAR_UUID_PLAIN = "0000aa01-0000-1000-8000-00805f9b34fb"
    CHAR_UUID_ENCRYPT = "0000ff01-0000-1000-8000-00805f9b34fb"

    # Protocol frame helpers
    @staticmethod
    def _checksum(data: bytes) -> int:
        return sum(data) & 0xFF

    @classmethod
    def build_frame(cls, func: int, cmd: int, payload: bytes = b"") -> bytes:
        """Build a DF DF protocol frame."""
        header = bytes([0xDF, 0xDF, func, cmd, len(payload)])
        body = header + payload
        return body + bytes([cls._checksum(body)])

    @classmethod
    def build_subscribe_cmd(cls, interval_ms: int = 1000) -> bytes:
        """Build Cmd 14 push subscription: enable=1, interval in ms (LE u16)."""
        payload = bytes([0x01, interval_ms & 0xFF, (interval_ms >> 8) & 0xFF])
        return cls.build_frame(0x03, 0x0E, payload)

    def __init__(self):
        self.client = None
        self._connected = False
        self._notify_enabled = False
        self._recv_queue = queue.Queue()
        self._running = False
        self._loop_thread = None
        self._loop = None
        self.write_char = None
        self.notify_char = None
        self.device_name = None
        self.device_address = None
        self.on_data_received = None
        self.on_disconnected = None

        self._subscribed = False
        self._interval_ms = 1000

    def _run_async(self, coro, timeout=30):
        import asyncio
        if not self._loop or not self._loop.is_running():
            self.start()
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def start(self):
        import asyncio
        if self._loop_thread and self._loop_thread.is_alive():
            return
        self._running = True

        def run_loop():
            import asyncio
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        for _ in range(20):
            if self._loop and self._loop.is_running():
                break
            time.sleep(0.05)

    def stop(self):
        self._running = False
        self._unsubscribe()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def scan_omniflux_devices(self, timeout: float = 5.0) -> List[dict]:
        import asyncio
        from bleak import BleakScanner

        devices = []

        def detection_callback(device, advertisement_data):
            if device.name and "OmniFlux" in device.name:
                if not any(d['address'] == device.address for d in devices):
                    devices.append({
                        'name': device.name,
                        'address': device.address,
                        'rssi': advertisement_data.rssi if advertisement_data else -100
                    })

        async def scan():
            scanner = BleakScanner(detection_callback)
            await scanner.start()
            await asyncio.sleep(timeout)
            await scanner.stop()
            return devices

        result = self._run_async(scan(), timeout=timeout+1)
        return sorted(result, key=lambda x: x['rssi'], reverse=True)

    def connect(self, address: str) -> bool:
        import asyncio
        from bleak import BleakClient

        async def connect_async():
            try:
                self.client = BleakClient(address, timeout=15.0, disconnected_callback=self._on_device_disconnected)
                await self.client.connect()

                if self.client.is_connected:
                    self._connected = True
                    self.device_address = address
                    try:
                        self.device_name = await self.client.get_device_name()
                    except Exception:
                        self.device_name = address

                    await self._find_characteristics()

                    if self.notify_char:
                        await self.client.start_notify(
                            self.notify_char.uuid,
                            self._notification_handler
                        )
                        self._notify_enabled = True

                    # Subscribe for push notifications
                    self._subscribe()
                    return True
            except Exception:
                pass
            return False

        return self._run_async(connect_async(), timeout=20)

    async def _find_characteristics(self):
        self.write_char = None
        self.notify_char = None

        for service in self.client.services:
            for char in service.characteristics:
                char_uuid = char.uuid.lower()
                if char_uuid == self.CHAR_UUID_PLAIN.lower():
                    self.write_char = char
                    self.notify_char = char
                    self.current_channel = "plain"
                elif char_uuid == self.CHAR_UUID_ENCRYPT.lower() and not self.write_char:
                    self.write_char = char
                    self.notify_char = char
                    self.current_channel = "encrypt"

    def _notification_handler(self, sender: int, data: bytes):
        self._recv_queue.put(data)
        if self.on_data_received:
            self.on_data_received(data)

    def _on_device_disconnected(self, client):
        """BLE 设备断开回调（设备关机、超出范围等）"""
        self._connected = False
        self._notify_enabled = False
        self._subscribed = False
        self.client = None
        if self.on_disconnected:
            self.on_disconnected()

    def _subscribe(self):
        """Send Cmd 14 to start push subscription."""
        if self._subscribed:
            return
        cmd = self.build_subscribe_cmd(self._interval_ms)
        ok = self.send(cmd)
        self._subscribed = ok

    def _unsubscribe(self):
        """Send Cmd 14 to stop push subscription."""
        if not self._subscribed or not self._connected:
            return
        payload = bytes([0x00, 0x00, 0x00])
        cmd = self.build_frame(0x03, 0x0E, payload)
        self.send(cmd)
        self._subscribed = False

    def disconnect(self):
        self._unsubscribe()

        async def disconnect_async():
            if self.client and self.client.is_connected:
                try:
                    if self.notify_char and self._notify_enabled:
                        await self.client.stop_notify(self.notify_char.uuid)
                except Exception:
                    pass
                try:
                    await self.client.disconnect()
                except Exception:
                    pass
            self._connected = False
            self._notify_enabled = False
            self.client = None

        try:
            self._run_async(disconnect_async(), timeout=5)
        except Exception:
            self._connected = False
            self._notify_enabled = False
            self.client = None

    def send(self, data: bytes) -> bool:
        if not self._connected or not self.client or not self.client.is_connected:
            return False
        if not self.write_char:
            return False

        async def send_async():
            await self.client.write_gatt_char(self.write_char.uuid, data)
            return True

        try:
            return self._run_async(send_async(), timeout=5)
        except Exception:
            return False

    def send_hex(self, hex_str: str) -> bool:
        try:
            hex_str = hex_str.strip().replace(' ', '').replace('-', '').replace(':', '')
            if len(hex_str) % 2 != 0:
                hex_str = '0' + hex_str
            data = bytes.fromhex(hex_str)
            return self.send(data)
        except Exception:
            return False

    def set_interval(self, interval_ms: int = 1000):
        """Change push interval. Resubscribes if already subscribed."""
        self._interval_ms = interval_ms
        if self._subscribed:
            self._unsubscribe()
            self._subscribe()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_notify_enabled(self) -> bool:
        return self._notify_enabled
