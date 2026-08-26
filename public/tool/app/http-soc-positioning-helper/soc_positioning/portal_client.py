from __future__ import annotations

from datetime import datetime
from typing import Callable

import requests

from soc_protocol import (
    FlightOption,
    SocProtocolClient,
    SocProtocolError,
    SocSessionExpired,
    StaffIdentity,
    SubmitOutcome,
    build_staff_validation_form,
    build_submit_form,
    choose_flight,
    credential_summary,
    flight_matches,
    format_credentials,
    parse_current_identity,
)

from .session_keepalive import SessionKeepAlive, random_keepalive_interval


PortalError = SocProtocolError
PortalSessionExpired = SocSessionExpired


class SocPortalClient:
    """APP 适配器：生产请求由 SOC protocol core 执行。"""

    def __init__(
        self,
        timeout: int = 30,
        session: requests.Session | None = None,
        keepalive_interval_factory: Callable[[], int] = random_keepalive_interval,
    ) -> None:
        self.protocol = SocProtocolClient(session=session, timeout_seconds=timeout)
        self.keepalive = SessionKeepAlive(
            keepalive_interval_factory,
            timeout,
            "http-soc-positioning-cookie-keepalive",
        )
        self.copyable_credentials = ""
        self.verified_at = ""

    @property
    def identity(self) -> dict[str, str] | None:
        return self.protocol.identity

    def load_credentials(self, source: str) -> dict[str, object]:
        self.clear_credentials()
        cookies, identity = self.protocol.load_credentials(source)
        self.copyable_credentials = format_credentials(cookies)
        self.verified_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return {
            **credential_summary(cookies),
            "verifiedAt": self.verified_at,
            "identity": dict(identity) if identity else None,
        }

    @staticmethod
    def _parse_identity(html: str) -> dict[str, str] | None:
        return parse_current_identity(html)

    def check_session(self) -> None:
        self.protocol.check_session()

    def invalidate_credentials(self) -> None:
        self.copyable_credentials = ""
        self.verified_at = ""
        self.protocol.clear_credentials()

    def clear_credentials(self) -> None:
        self.keepalive.stop()
        self.invalidate_credentials()

    def close(self) -> None:
        self.keepalive.stop()
        self.protocol.close()

    def suggest(self, pinyin: str) -> list[str]:
        _response, suggestions = self.protocol.station_suggestions(pinyin)
        return suggestions

    def list_flights(self, flight_date: str, departure: str, arrival: str) -> list[FlightOption]:
        _response, options = self.protocol.flight_options(flight_date, departure, arrival)
        return options

    @staticmethod
    def _flight_match(option: FlightOption, requested: str) -> bool:
        return flight_matches(option, requested)

    @staticmethod
    def choose_flight(options: list[FlightOption], requested: str) -> FlightOption:
        return choose_flight(options, requested)

    def validate_staff(self, record: dict[str, object], option: FlightOption) -> StaffIdentity:
        form = build_staff_validation_form(
            str(record["员工号"]),
            str(record["出发地"]),
            str(record["目的地"]),
            str(record["航班日期"]),
            str(record["申请原因代码"]),
            option.route,
        )
        _response, identity = self.protocol.validate_staff(form)
        _mobile_response, mobile = self.protocol.staff_mobile(identity.employee_id)
        return StaffIdentity(identity.employee_id, identity.name, mobile)

    def submit(
        self,
        record: dict[str, object],
        option: FlightOption,
        identity: StaffIdentity,
    ) -> SubmitOutcome:
        form = build_submit_form(
            identity=identity,
            flight_date=str(record["航班日期"]),
            departure=str(record["出发地"]),
            arrival=str(record["目的地"]),
            option_value=option.value,
            reason_code=str(record["申请原因代码"]),
            comment=str(record.get("备注") or ""),
        )
        _response, outcome = self.protocol.submit(form)
        return outcome
