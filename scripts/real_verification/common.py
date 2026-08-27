from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_ROOT = ROOT / "public" / "tool" / "app" / "_shared"
API_DOCS_ROOT = ROOT / "public" / "tool" / "app" / "api-docs"
SYSTEM_ALIASES = {
    "ieb": ("IEB", "门户"),
    "oa": ("OA", "oa"),
    "caac": ("CAAC", "执照", "云桌面"),
    "soc": ("SOC",),
}
INPUT_SECTION_ALIASES = ("验收参数", "TEST")
SECRET_PATTERN = re.compile(
    r"(?i)(JSESSIONID|iebJSid|SESSION|ROUTE-SESSION|yzzzm|home|cookiesession1)\s*=\s*[^;\s]+"
)


@dataclass(frozen=True)
class CaseResult:
    system: str
    entry: str
    status: str
    detail: str
    write: bool = False


def redact(value: object) -> str:
    text = str(value or "")
    text = SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=[已隐藏]", text)
    return text[:500]


def _section(text: str, aliases: tuple[str, ...]) -> str:
    heading = "|".join(re.escape(alias) for alias in aliases)
    match = re.search(rf"(?ims)^##\s+(?:{heading})\s*$\n(?P<body>.*?)(?=^##\s+|\Z)", text)
    return match.group("body").strip() if match else ""


def _legacy_section(text: str, aliases: tuple[str, ...]) -> str:
    label = "|".join(re.escape(alias) for alias in aliases)
    match = re.search(
        rf"(?ims)^\s*(?:{label})\s*[:：]\s*(?P<body>.*?)(?=^\s*(?:门户|IEB|OA|oa|SOC|执照|CAAC|云桌面)\s*[:：]|\Z)",
        text,
    )
    return match.group("body").strip() if match else ""


def load_credential_sections(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    return {system: _section(text, aliases) or _legacy_section(text, aliases) for system, aliases in SYSTEM_ALIASES.items()}


def load_verification_inputs(path: Path) -> dict[str, str]:
    """读取本地 Markdown 的 JSON 验收参数；旧 cookie.txt 可不提供该段。"""
    text = path.read_text(encoding="utf-8")
    section = _section(text, INPUT_SECTION_ALIASES)
    if not section:
        return {}
    fenced = re.search(r"(?is)```(?:json)?\s*(\{.*?\})\s*```", section)
    raw = fenced.group(1) if fenced else section.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError("验收参数必须是有效 JSON 对象") from error
    if not isinstance(payload, dict):
        raise ValueError("验收参数必须是 JSON 对象")
    return {str(key): str(value or "").strip() for key, value in payload.items()}


def configure_import_paths() -> None:
    for path in (SHARED_ROOT, API_DOCS_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def result_summary(payload: dict[str, object]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return "未返回结构化 data"
    summary = data.get("summary")
    tables = data.get("tables")
    pieces: list[str] = []
    if isinstance(summary, dict):
        for key in (
            "recordCount", "total", "pages", "fieldCount", "optionCount", "sectionCount",
            "topLevelKeyCount", "scanned", "eligible", "skipped", "requested", "target",
            "success", "failed", "resultCount", "conflictCount", "lockStatuses", "outcome",
        ):
            if key in summary:
                pieces.append(f"{key}={summary[key]}")
    if isinstance(tables, list):
        pieces.append(f"tables={len(tables)}")
        counts = [str(len(item.get("rows", []))) for item in tables if isinstance(item, dict)]
        if counts:
            pieces.append("rows=" + ",".join(counts[:12]))
    return "，".join(pieces) or "结构化 data 已返回"


def is_session_failure(error: BaseException) -> bool:
    name = error.__class__.__name__.lower()
    text = str(error).lower()
    return "sessionexpired" in name or "会话已失效" in text or "cookie 已失效" in text or "登录凭据已失效" in text


def describe(value: object) -> str:
    if isinstance(value, dict):
        return json.dumps({key: value[key] for key in ("status", "reason", "endpointId") if key in value}, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return f"返回 {len(value)} 项"
    return str(value)[:300]
