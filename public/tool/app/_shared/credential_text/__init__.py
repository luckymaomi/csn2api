from __future__ import annotations

import re


def normalize_credential_source(source: str) -> str:
    """撤销聊天或富文本复制引入的 Markdown 转义，不解释系统凭据。"""
    text = str(source or "")
    text = re.sub(r"\[(https?://[^\]\s]+)\]\(\1\)", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"\\([_*])", r"\1", text)
    return re.sub(
        r"(?m)(^|\s)\\(--(?:data-raw|data|compressed)\b)",
        r"\1\2",
        text,
    )


__all__ = ["normalize_credential_source"]
