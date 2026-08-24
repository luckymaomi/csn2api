"""Stable models for the SOC positioning workbench."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InputPayload:
    input_mode: str = "excel"
    excel_name: str = ""
    excel_bytes: bytes | None = None
    pasted_text: str = ""
    common_remark: str = ""


@dataclass(frozen=True)
class StaffIdentity:
    employee_id: str
    name: str
    mobile: str


@dataclass(frozen=True)
class FlightOption:
    display_number: str
    flight_number: str
    sequence_number: str
    flight_date: str
    route: str
    flight_time: str
    crew_departure: str
    subfleet_type: str
    airline_code: str
    value: str


@dataclass(frozen=True)
class SubmitOutcome:
    success: bool
    message: str
