"""OmniFlux — 本地 Web 调试工具入口"""
import sys
import os
import threading
import webbrowser
import time
import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)
os.environ["PYTHONWARNINGS"] = "ignore"


def open_browser(port: int):
    """延迟打开浏览器（等待服务器启动）"""
    time.sleep(1.2)
    webbrowser.open(f"http://localhost:{port}")


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
