from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from http_qualification_monitor.manager import RunManager
from http_qualification_monitor.server import create_server


APP_ROOT = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动资质监控（皇帝版）")
    parser.add_argument("--port", type=int, default=0, help="本地端口，默认随机分配")
    parser.add_argument("--no-open", action="store_true", help="不自动打开工作台页面")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manager = RunManager(APP_ROOT / "results")
    server = create_server(APP_ROOT, args.port, manager)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if not args.no_open:
        webbrowser.open(url)
    print(f"资质监控工作台已启动：{url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n资质监控工作台已关闭。")
    finally:
        manager.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
