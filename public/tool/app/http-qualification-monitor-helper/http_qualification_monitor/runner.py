from __future__ import annotations

from collections.abc import Callable

from ieb_protocol.qualification_monitor_models import QualificationGroup, QualificationItem

from .exporter import NativeExportStore
from .models import ExportSummary
from .portal_client import PortalSessionExpired


EventCallback = Callable[[dict[str, object]], None]
StopCallback = Callable[[], bool]


class ExportRunner:
    def __init__(
        self,
        client: object,
        store: NativeExportStore,
        event_callback: EventCallback,
        should_stop: StopCallback | None = None,
    ) -> None:
        self.client = client
        self.store = store
        self.event_callback = event_callback
        self.should_stop = should_stop or (lambda: False)

    def run_all(self, groups: list[QualificationGroup]) -> ExportSummary:
        entries = [(group, item) for group in groups for item in group.items]
        return self._run(entries, complete_batch=True)

    def run_one(self, groups: list[QualificationGroup], code: str) -> ExportSummary:
        matches = [(group, item) for group in groups for item in group.items if item.code == code]
        if len(matches) != 1:
            raise ValueError("未找到唯一资质子类")
        return self._run(matches, complete_batch=False)

    def _run(
        self,
        entries: list[tuple[QualificationGroup, QualificationItem]],
        *,
        complete_batch: bool,
    ) -> ExportSummary:
        files: dict[str, object] = {}
        errors: dict[str, str] = {}
        interrupted = False
        session_expired = False
        for index, (group, item) in enumerate(entries, start=1):
            if self.should_stop():
                interrupted = True
                break
            self.event_callback({"type": "item_started", "code": item.code, "name": item.name})
            try:
                content = self.client.export_qualification(item.code)  # type: ignore[attr-defined]
                path = self.store.save(group, item, index, content)
                files[item.code] = path
                self.event_callback({"type": "item_succeeded", "code": item.code, "path": path})
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
        archive = None
        if complete_batch and not interrupted and not session_expired and not errors and len(files) == len(entries):
            archive = self.store.build_archive()
        return ExportSummary(
            total=len(entries),
            success=len(files),
            failed=len(errors),
            files=files,  # type: ignore[arg-type]
            errors=errors,
            archive=archive,
            interrupted=interrupted,
            session_expired=session_expired,
        )
