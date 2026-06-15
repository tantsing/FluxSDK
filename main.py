"""OmniFlux — 本地 Web 调试工具入口"""
import sys
import os
import threading
import webbrowser
import time
import subprocess
import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["PYTHONWARNINGS"] = "ignore"


def open_browser(port: int):
    """Wait for server to be ready, then open browser"""
    import urllib.request

    url = f"http://localhost:{port}"

    # Wait for server to actually start (up to 10 seconds)
    for _ in range(20):
        time.sleep(0.5)
        try:
            resp = urllib.request.urlopen(url)
            resp.close()
            break
        except Exception:
            pass

    # Open browser — try multiple strategies per platform
    try:
        webbrowser.open(url)
    except Exception:
        pass

    time.sleep(0.5)

    # Fallback: platform-native open
    try:
        if sys.platform == "win32":
            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.run(["open", url], timeout=5)
        else:
            subprocess.run(["xdg-open", url], timeout=5)
    except Exception:
        pass


def main():
    host = "0.0.0.0"
    port = 8765

    print(f"\n  OmniFlux 调试工具")
    print(f"  本地访问: http://localhost:{port}")
    print(f"  按 Ctrl+C 退出\n")

    # 启动浏览器
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    # 启动服务器
    from backend.server import run_server
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
