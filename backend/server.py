import asyncio
import os
import sys
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.data_store import DataStore
from backend.models import (
    ConnectRequest, IntervalRequest, FieldsRequest, FIELD_META
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("omniflux")

store = DataStore()
app = FastAPI(title="OmniFlux", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== REST API ====================

@app.get("/api/status")
def get_status():
    return store.get_status().model_dump()


@app.get("/api/devices")
def get_devices():
    return {"devices": getattr(store, '_cached_devices', [])}


@app.post("/api/scan")
def trigger_scan():
    store.scanning = True
    try:
        store.debugger.start()
        devices = store.debugger.scan_omniflux_devices(timeout=5.0)
        store._cached_devices = devices
    except Exception as e:
        logger.error(f"扫描失败: {e}")
        store._cached_devices = []
    finally:
        store.scanning = False
    return {"devices": store._cached_devices}


@app.post("/api/connect")
def connect_device(req: ConnectRequest):
    store.debugger.start()
    ok = store.debugger.connect(req.address)
    return {"success": ok, "device_name": store.debugger.device_name}


@app.post("/api/disconnect")
def disconnect_device():
    store.debugger.disconnect()
    return {"success": True}


@app.post("/api/interval")
def set_interval(req: IntervalRequest):
    ms = int(req.interval * 1000)
    store.debugger.set_interval(ms)
    return {"success": True, "interval": req.interval}


@app.get("/api/fields")
def get_fields():
    return {
        "all": FIELD_META,
        "selected": list(store.selected_fields) if store.selected_fields else list(FIELD_META.keys())
    }


@app.post("/api/fields")
def update_fields(req: FieldsRequest):
    store.selected_fields = set(req.fields)
    return {"success": True, "selected": list(store.selected_fields)}


@app.get("/api/latest")
def get_latest():
    data = store.latest_data
    if data is None:
        return {"data": None}
    return {"data": data.model_dump()}


@app.get("/api/datafile")
def get_data_file():
    """返回数据文件路径和内容，供前端展示"""
    try:
        with open(store.data_file, 'r') as f:
            content = f.read().strip()
    except Exception:
        content = ""
    return {"path": store.data_file, "content": content}


# ==================== WebSocket ====================

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    q = store.subscribe()

    try:
        while True:
            try:
                payload = await asyncio.wait_for(q.get(), timeout=1.0)
                if isinstance(payload, dict) and "type" in payload:
                    await ws.send_json(payload)
                else:
                    await ws.send_json({"type": "data", "payload": payload})
            except asyncio.TimeoutError:
                # No new data yet — keep connection alive
                continue
    except WebSocketDisconnect:
        pass
    finally:
        store.unsubscribe(q)


# ==================== 静态文件 ====================

# Resolve frontend directory (handles PyInstaller frozen mode)
if getattr(sys, 'frozen', False):
    _base_dir = sys._MEIPASS
else:
    _base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_frontend_dir = os.path.join(_base_dir, "frontend")

@app.get("/")
async def serve_frontend():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(_frontend_dir, "index.html"))


def run_server(host: str = "0.0.0.0", port: int = 8765):
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")
