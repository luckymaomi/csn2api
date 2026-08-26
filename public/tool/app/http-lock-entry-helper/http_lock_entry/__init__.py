"""IEB 锁班本地工作台。"""

import sys
from pathlib import Path


_shared_root = Path(__file__).resolve().parents[2] / "_shared"
if _shared_root.is_dir() and str(_shared_root) not in sys.path:
    sys.path.insert(0, str(_shared_root))
