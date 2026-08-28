from __future__ import annotations

import sys
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
SHARED_ROOT = APP_ROOT.parent / "_shared"
if SHARED_ROOT.is_dir() and str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from csn2api_runtime.single_app import main


if __name__ == "__main__":
    raise SystemExit(main(APP_ROOT))
