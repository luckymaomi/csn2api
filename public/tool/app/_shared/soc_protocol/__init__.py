"""SOC 随机置位共享 HTTP 协议核心。"""

from .client import SocProtocolClient
from .contract import (
    APPLY_REASON_CODES,
    APPLY_REASON_LABELS,
    APPLY_REASONS,
    BASE_URL,
    FLIGHTS_PATH,
    HOT_CITIES,
    NAVIGATION_PATH,
    PAGE_PATH,
    REASONS_PATH,
    STAFF_MOBILE_PATH,
    STAFF_VALIDATE_PATH,
    SUBMIT_PATH,
    SUGGEST_PATH,
    SocContractError,
    SocProtocolError,
    SocSessionExpired,
    build_staff_validation_form,
    build_submit_form,
    choose_flight,
    flight_matches,
    parse_current_identity,
    parse_flight_options,
    parse_staff_identity,
    parse_station_suggestions,
    parse_submit_outcome,
)
from .credentials import credential_summary, format_credentials, parse_credentials
from .models import FlightOption, StaffIdentity, SubmitOutcome

__all__ = [
    "APPLY_REASON_CODES", "APPLY_REASON_LABELS", "APPLY_REASONS", "BASE_URL", "FLIGHTS_PATH",
    "HOT_CITIES", "NAVIGATION_PATH", "PAGE_PATH", "REASONS_PATH", "STAFF_MOBILE_PATH",
    "STAFF_VALIDATE_PATH", "SUBMIT_PATH", "SUGGEST_PATH", "FlightOption", "SocContractError",
    "SocProtocolClient", "SocProtocolError", "SocSessionExpired", "StaffIdentity", "SubmitOutcome",
    "build_staff_validation_form", "build_submit_form", "choose_flight", "credential_summary",
    "flight_matches", "format_credentials", "parse_credentials", "parse_current_identity",
    "parse_flight_options", "parse_staff_identity", "parse_station_suggestions", "parse_submit_outcome",
]
