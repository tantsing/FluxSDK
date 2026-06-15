"""OmniFlux — 本地 Web 调试工具入口"""
import sys
import os
import threading
import time
import subprocess
import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["PYTHONWARNINGS"] = "ignore"


def main():
    host = "0.0.0.0"
    port = 8765

    print(f"\n  OmniFlux 调试工具")
    print(f"  本地访问: http://localhost:{port}")
    print(f"  按 Ctrl+C 退出\n")

    from backend.server import run_server, store

    # Start HTTP server in background thread
    threading.Thread(
        target=run_server,
        args=(host, port),
        daemon=True,
    ).start()

    # Start MODBUS TCP server (port 502, for Artisan connection)
    modbus_port = 502
    from backend.modbus_server import run_modbus_server
    threading.Thread(
        target=run_modbus_server,
        args=(store, host, modbus_port),
        daemon=True,
    ).start()
    print(f"  MODBUS TCP: localhost:{modbus_port}")

    # Wait for server to be ready, then open browser
    import urllib.request
    url = f"http://localhost:{port}"

    for _ in range(40):
        time.sleep(0.5)
        try:
            resp = urllib.request.urlopen(url)
            resp.close()
            print(f"  浏览器已打开 — {url}")
            break
        except Exception:
            pass

    try:
        if sys.platform == "win32":
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        print(f"  请手动打开浏览器访问: {url}")

    # Keep running until Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n  已退出")


if __name__ == "__main__":
    main()
