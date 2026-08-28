from __future__ import annotations

import argparse
import re
import webbrowser
from pathlib import Path

from .application import close_application_server, create_application_server
from .interrupts import install_interrupt_handlers


def _title(app_root: Path) -> str:
    page = app_root / "web" / "index.html"
    if page.is_file():
        match = re.search(r"<title>(.*?)</title>", page.read_text(encoding="utf-8"), re.I | re.S)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return app_root.name


def main(app_root: Path) -> int:
    parser = argparse.ArgumentParser(description=f"启动{_title(app_root)}")
    parser.add_argument("--port", type=int, default=0, help="本地端口，默认随机分配")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()
    install_interrupt_handlers()
    server = create_application_server(app_root, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"{_title(app_root)}：{url}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{_title(app_root)}已关闭。")
    finally:
        close_application_server(server, shutdown=False)
    return 0
