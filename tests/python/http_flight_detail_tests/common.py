from __future__ import annotations

import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "http-flight-detail-helper"
SHARED_ROOT = REPOSITORY_ROOT / "public" / "tool" / "app" / "_shared"
for root in (APP_ROOT, SHARED_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

