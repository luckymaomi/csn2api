from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from soc_positioning.server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="启动 SOC 随机置位批量工作台")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    server = create_server(Path(__file__).resolve().parent, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"SOC 随机置位批量工作台：{url}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.run_manager.shutdown()  # type: ignore[attr-defined]
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
