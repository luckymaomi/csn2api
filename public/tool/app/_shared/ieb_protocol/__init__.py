"""IEB 飞行门户共享 HTTP 协议核心。"""

from .base import (
    BASE_URL,
    IebContractError,
    IebProtocolError,
    IebSession,
    IebSessionExpired,
    credential_summary,
    format_credentials,
    parse_credentials,
)
from .flight_detail import FlightDetailProtocol
from .flight_detail_contract import DETAIL_HEADERS

__all__ = [
    "BASE_URL",
    "IebContractError",
    "IebProtocolError",
    "IebSession",
    "IebSessionExpired",
    "credential_summary",
    "format_credentials",
    "parse_credentials",
    "FlightDetailProtocol",
    "DETAIL_HEADERS",
]
