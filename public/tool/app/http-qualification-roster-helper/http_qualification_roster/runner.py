from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .exporter import RosterWorkbook
from ieb_protocol.roster_models import OperatingQualification, PersonQualification, QueryFilters
from .portal_client import PortalError, PortalSessionExpired


EventCallback = Callable[[dict[str, object]], None]
StopCallback = Callable[[], bool]


@dataclass(frozen=True)
class RunSummary:
    total: int
    success: int
    failed: int
    relationship_count: int
    errors: dict[str, str] = field(default_factory=dict)
    interrupted: bool = False
    session_expired: bool = False


class RosterRunner:
    def __init__(
        self,
        client: object,
        workbook: RosterWorkbook,
        event_callback: EventCallback,
        should_stop: StopCallback | None = None,
    ) -> None:
        self.client = client
        self.workbook = workbook
        self.event_callback = event_callback
        self.should_stop = should_stop or (lambda: False)

    def run(
        self,
        filters: QueryFilters,
        qualifications: list[OperatingQualification],
    ) -> RunSummary:
        success = 0
        errors: dict[str, str] = {}
        interrupted = False
        session_expired = False
        for item in qualifications:
            if self.should_stop():
                interrupted = True
                break
            self.event_callback({"type": "item_started", "code": item.code, "name": item.name})
            try:
                count = self.client.query_count(filters, item.code)  # type: ignore[attr-defined]
                people = self.client.export_people(filters, item.code)  # type: ignore[attr-defined]
                if count != len(people):
                    raise PortalError(f"查询人数 {count} 与普通导出人数 {len(people)} 不一致")
                relations = [PersonQualification(person.staff_number, person.name, item.code) for person in people]
                added = self.workbook.append_qualification(item.code, relations)
                if len(added) != count:
                    raise PortalError("普通导出人数与查询人数不一致")
                success += 1
                self.event_callback({
                    "type": "item_succeeded",
                    "code": item.code,
                    "count": count,
                    "relations": [relation.to_dict(0) for relation in added],
                })
            except PortalSessionExpired as error:
                message = str(error)
                errors[item.code] = message
                self.event_callback({"type": "item_failed", "code": item.code, "error": message})
                session_expired = True
                break
            except Exception as error:
                message = str(error) or error.__class__.__name__
                errors[item.code] = message
                self.event_callback({"type": "item_failed", "code": item.code, "error": message})
        return RunSummary(
            total=len(qualifications),
            success=success,
            failed=len(errors),
            relationship_count=len(self.workbook.relations),
            errors=errors,
            interrupted=interrupted,
            session_expired=session_expired,
        )
