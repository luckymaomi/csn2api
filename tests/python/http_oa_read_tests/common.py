from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "http-oa-read-helper"
SHARED_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "_shared"
for path in (APP_ROOT, SHARED_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
