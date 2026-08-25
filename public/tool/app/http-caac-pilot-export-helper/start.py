from __future__ import annotations

import argparse
import webbrowser
from pathlib import Path

from caac_pilot_export.server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="CAAC 飞行员全量信息导出")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()
    server = create_server(Path(__file__).resolve().parent, args.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"CAAC 飞行员全量信息导出：{url}")
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
