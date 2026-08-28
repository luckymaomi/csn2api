from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SHARED_RUNTIME = ROOT / "public" / "tool" / "app" / "_shared"
if str(SHARED_RUNTIME) not in sys.path:
    sys.path.insert(0, str(SHARED_RUNTIME))

from csn2api_runtime.gateway import create_gateway_server  # noqa: E402
from csn2api_runtime.interrupts import install_interrupt_handlers  # noqa: E402
from csn2api_runtime.lease import AccessLease  # noqa: E402
from csn2api_runtime.supervisor import RuntimeSupervisor, RuntimeTarget  # noqa: E402


PORT = 4567


def build_dist(project_root: Path) -> None:
    npm_command = "npm.cmd" if os.name == "nt" else "npm"
    print("[csn2api] 正在构建统一运行目录...")
    subprocess.run([npm_command, "run", "build"], cwd=project_root, check=True)


def load_targets(dist_root: Path) -> list[RuntimeTarget]:
    manifest = json.loads((dist_root / "runtime-tools.json").read_text(encoding="utf-8"))
    tools = [
        RuntimeTarget(
            entry=str(item["entry"]),
            name=str(item["name"]),
            app_root=dist_root / "tool" / "app" / str(item["entry"]),
            system_id=str(item["systemId"]),
        )
        for item in manifest["tools"]
    ]
    tools.append(RuntimeTarget("api-docs", "API 文档", dist_root / "tool" / "app" / "api-docs"))
    return tools


def local_addresses(port: int) -> list[str]:
    addresses = {"127.0.0.1"}
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return [f"http://{address}:{port}/" for address in sorted(addresses) if ":" not in address]


def check_layout(project_root: Path) -> None:
    app_root = project_root / "public" / "tool" / "app"
    workbenches = sorted(
        root for root in app_root.glob("http-*-helper") if (root / "web" / "index.html").is_file()
    )
    if not workbenches:
        raise RuntimeError("没有发现可运行的 HTTP 工作台")
    for root in workbenches:
        if not (root / "start.py").is_file():
            raise RuntimeError(f"{root.name} 缺少统一 start.py")
    if not (app_root / "api-docs" / "start.py").is_file():
        raise RuntimeError("API 文档缺少独立启动入口")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="启动 csn2api 局域网统一工作台")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址，默认允许局域网访问")
    parser.add_argument("--port", type=int, default=PORT, help="统一入口端口")
    parser.add_argument("--idle-minutes", type=float, default=3, help="无活动自动释放分钟数")
    parser.add_argument("--no-build", action="store_true", help="跳过构建")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--check", action="store_true", help="验证入口结构后退出")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    install_interrupt_handlers()
    supervisor: RuntimeSupervisor | None = None
    gateway = None
    try:
        check_layout(ROOT)
        if args.check:
            print("[csn2api] start_all.py check passed.")
            return 0
        if not args.no_build:
            build_dist(ROOT)
        dist_root = ROOT / "dist"
        if not (dist_root / "runtime-tools.json").is_file():
            raise RuntimeError("缺少 dist/runtime-tools.json，请先执行构建")
        supervisor = RuntimeSupervisor(load_targets(dist_root))
        supervisor.start_all()
        lease = AccessLease(idle_timeout_seconds=args.idle_minutes * 60)
        gateway = create_gateway_server(dist_root, supervisor, lease, args.host, args.port)
        actual_port = int(gateway.server_address[1])
        print("[csn2api] 局域网统一工作台已启动：")
        for url in local_addresses(actual_port):
            print(f"  {url}")
        if not args.no_open:
            webbrowser.open(f"http://127.0.0.1:{actual_port}/")
        try:
            gateway.serve_forever()
        except KeyboardInterrupt:
            print("\n[csn2api] 正在关闭全部工作台...")
        finally:
            gateway.server_close()
            gateway = None
            supervisor.stop_all()
            supervisor = None
        return 0
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError) as error:
        if gateway is not None:
            gateway.server_close()
        if supervisor is not None:
            supervisor.stop_all()
        print(f"[csn2api] 启动失败：{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
