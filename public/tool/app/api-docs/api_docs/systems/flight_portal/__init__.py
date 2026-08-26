"""IEB API 文档系统适配器。"""

from .adapter import FlightPortalAdapter
from .common import random_keepalive_interval

__all__ = ["FlightPortalAdapter", "random_keepalive_interval"]
