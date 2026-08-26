from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

try:
    from .common import APP_ROOT, ooxml_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, ooxml_bytes  # type: ignore[no-redef]  # noqa: F401
from http_qualification_monitor.exporter import NativeExportStore
from ieb_protocol.qualification_monitor_models import QualificationGroup, QualificationItem
from http_qualification_monitor.portal_client import PortalSessionExpired
from http_qualification_monitor.runner import ExportRunner


GROUPS = [
    QualificationGroup("资质运行类", "ZZYX", [
        QualificationItem("第一项", "A"),
        QualificationItem("第二/项", "B"),
    ]),
    QualificationGroup("资质资格类", "ZZZG", [QualificationItem("第三项", "C")]),
    QualificationGroup("资质特殊类", "ZZTS", [QualificationItem("第四项", "D")]),
]


class RecordingClient:
    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.calls: list[str] = []
        self.active = 0
        self.maximum_active = 0
        self.failures = failures or {}

    def export_qualification(self, code: str) -> bytes:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        self.calls.append(code)
        try:
            if code in self.failures:
                raise self.failures[code]
            return ooxml_bytes(code)
        finally:
            self.active -= 1


class RunnerExporterTests(unittest.TestCase):
    def test_all_export_is_serial_and_complete_zip_uses_three_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            client = RecordingClient()
            store = NativeExportStore(Path(directory), "run-1")
            events: list[dict[str, object]] = []
            summary = ExportRunner(client, store, events.append).run_all(GROUPS)

            self.assertEqual(client.calls, ["A", "B", "C", "D"])
            self.assertEqual(client.maximum_active, 1)
            self.assertEqual((summary.total, summary.success, summary.failed), (4, 4, 0))
            self.assertIsNotNone(summary.archive)
            with zipfile.ZipFile(summary.archive) as archive:
                names = archive.namelist()
            self.assertEqual({name.split("/")[0] for name in names}, {"资质运行类", "资质资格类", "资质特殊类"})
            self.assertTrue(any("第二_项_B.xlsx" in name for name in names))

    def test_native_bytes_are_saved_unchanged_and_failure_skips_complete_zip(self) -> None:
        native = ooxml_bytes("unchanged")

        class Client(RecordingClient):
            def export_qualification(self, code: str) -> bytes:
                if code == "B":
                    raise RuntimeError("虚构失败")
                return native

        with tempfile.TemporaryDirectory() as directory:
            store = NativeExportStore(Path(directory), "run-2")
            summary = ExportRunner(Client(), store, lambda _event: None).run_all(GROUPS)
            self.assertEqual(summary.failed, 1)
            self.assertIsNone(summary.archive)
            self.assertTrue(all(path.read_bytes() == native for path in summary.files.values()))

    def test_session_expiry_stops_immediately_and_stop_is_checked_between_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            expired = RecordingClient({"B": PortalSessionExpired("过期")})
            summary = ExportRunner(expired, NativeExportStore(Path(directory), "run-3"), lambda _event: None).run_all(GROUPS)
            self.assertEqual(expired.calls, ["A", "B"])
            self.assertTrue(summary.session_expired)

        stop = False

        class StopClient(RecordingClient):
            def export_qualification(self, code: str) -> bytes:
                nonlocal stop
                value = super().export_qualification(code)
                stop = True
                return value

        with tempfile.TemporaryDirectory() as directory:
            stopped = StopClient()
            summary = ExportRunner(stopped, NativeExportStore(Path(directory), "run-4"), lambda _event: None, lambda: stop).run_all(GROUPS)
            self.assertEqual(stopped.calls, ["A"])
            self.assertTrue(summary.interrupted)


if __name__ == "__main__":
    unittest.main()
