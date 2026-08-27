from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_ROOT = ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from real_verification.common import (  # noqa: E402
    load_credential_sections,
    load_verification_inputs,
    redact,
    result_summary,
)
from real_verification.runner import RealVerifier  # noqa: E402
from real_verification.app_http import require_completed, verify_frontend_route  # noqa: E402


class RealVerificationCoreTests(unittest.TestCase):
    def test_markdown_keeps_credentials_and_inputs_in_local_file(self) -> None:
        content = """# 本地验收
## 验收参数
```json
{"iebStaffNumber":"900001","caacPilotName":"样例人员"}
```
## IEB
Cookie: JSESSIONID=ieb-session; iebJSid=ieb-browser
## OA
Cookie: SESSION=oa-session
## CAAC
Cookie: yzzzm=one; JSESSIONID=two; home=three
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cookies.local.md"
            path.write_text(content, encoding="utf-8")
            sections = load_credential_sections(path)
            inputs = load_verification_inputs(path)
        self.assertIn("iebJSid=ieb-browser", sections["ieb"])
        self.assertIn("SESSION=oa-session", sections["oa"])
        self.assertIn("home=three", sections["caac"])
        self.assertEqual(inputs["iebStaffNumber"], "900001")
        self.assertEqual(inputs["caacPilotName"], "样例人员")

    def test_result_output_redacts_session_values_and_keeps_business_counts(self) -> None:
        self.assertEqual(redact("JSESSIONID=secret; SESSION=other"), "JSESSIONID=[已隐藏]; SESSION=[已隐藏]")
        summary = result_summary({
            "data": {
                "summary": {"total": 18, "eligible": 14, "success": 1, "lockStatuses": ["待审批"]},
                "tables": [{"rows": [{"status": "成功"}]}],
            }
        })
        self.assertIn("total=18", summary)
        self.assertIn("success=1", summary)
        self.assertIn("lockStatuses=['待审批']", summary)
        self.assertIn("rows=1", summary)

    def test_case_selection_and_write_allowance_are_independent(self) -> None:
        verifier = RealVerifier({}, {}, "both", "all", {"oa-read"}, True, "", 1)
        self.assertFalse(verifier.selected("ieb"))
        self.assertTrue(verifier.selected("oa"))
        self.assertTrue(verifier.selected_case("oa-read"))
        self.assertFalse(verifier.selected_case("flight-stats"))
        self.assertTrue(verifier.claim_write("oa"))
        self.assertFalse(verifier.claim_write("oa"))

    def test_failed_app_verification_reports_the_item_error(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "门户返回 HTTP 500"):
            require_completed({
                "phase": "partial_failure",
                "progress": {"success": 0},
                "items": [{"status": "failed", "error": "飞行门户返回 HTTP 500"}],
            })

    def test_frontend_route_requires_every_declared_runtime_asset(self) -> None:
        page = Mock(status_code=200, text="""
            <script src="./theme.js"></script>
            <link rel="stylesheet" href="./libs/bootstrap.min.css">
            <link rel="stylesheet" href="./theme.css">
            <link rel="stylesheet" href="./styles.css">
        """)
        script = Mock(status_code=200, text='/api/run import("./session_keepalive.mjs")')
        responses = {
            "http://127.0.0.1:1234/": page,
            "http://127.0.0.1:1234/theme.js": Mock(status_code=200, content=b"theme"),
            "http://127.0.0.1:1234/libs/bootstrap.min.css": Mock(status_code=200, content=b"bootstrap"),
            "http://127.0.0.1:1234/theme.css": Mock(status_code=200, content=b"theme-style"),
            "http://127.0.0.1:1234/styles.css": Mock(status_code=404, content=b""),
            "http://127.0.0.1:1234/app.mjs": script,
            "http://127.0.0.1:1234/session_keepalive.mjs": Mock(status_code=200, content=b"keepalive"),
        }
        with patch("real_verification.app_http.requests.get", side_effect=lambda url, **_kwargs: responses[url]):
            with self.assertRaisesRegex(RuntimeError, "styles.css"):
                verify_frontend_route("http://127.0.0.1:1234", "/api/run")

    def test_frontend_route_accepts_complete_runtime_and_bound_route(self) -> None:
        page = Mock(status_code=200, content=b"page", text="""
            <script src='./theme.js'></script>
            <link href='./libs/bootstrap.min.css' rel='stylesheet'>
            <link href='./theme.css' rel='stylesheet'>
            <link href='./styles.css' rel='stylesheet'>
        """)
        responses = {
            "http://127.0.0.1:1234/": page,
            "http://127.0.0.1:1234/theme.js": Mock(status_code=200, content=b"theme"),
            "http://127.0.0.1:1234/libs/bootstrap.min.css": Mock(status_code=200, content=b"bootstrap"),
            "http://127.0.0.1:1234/theme.css": Mock(status_code=200, content=b"theme-style"),
            "http://127.0.0.1:1234/styles.css": Mock(status_code=200, content=b"page-style"),
            "http://127.0.0.1:1234/app.mjs": Mock(status_code=200, content=b"script", text='/api/run'),
            "http://127.0.0.1:1234/session_keepalive.mjs": Mock(status_code=200, content=b"keepalive"),
        }
        with patch("real_verification.app_http.requests.get", side_effect=lambda url, **_kwargs: responses[url]) as get:
            verify_frontend_route("http://127.0.0.1:1234", "/api/run")
        self.assertEqual(get.call_count, len(responses))


if __name__ == "__main__":
    unittest.main()
