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


def open_browser(port: int):
    """Wait for server to be ready, then open browser using native OS calls"""
    import urllib.request

    url = f"http://localhost:{port}"

    # Wait for server to start (up to 15 seconds for slow PyInstaller startup)
    for _ in range(30):
        time.sleep(0.5)
        try:
            resp = urllib.request.urlopen(url)
            resp.close()
            break
        except Exception:
            pass

    # Launch browser via OS-native call
    try:
        if sys.platform == "win32":
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def main():
    host = "0.0.0.0"
    port = 8765

    print(f"\n  OmniFlux 调试工具")
    print(f"  本地访问: http://localhost:{port}")
    print(f"  按 Ctrl+C 退出\n")

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    from backend.server import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
