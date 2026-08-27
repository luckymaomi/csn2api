from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


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
from real_verification.app_http import require_completed  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
