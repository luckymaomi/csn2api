from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED_ROOT = ROOT / "public" / "tool" / "app" / "_shared"
if str(SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(SHARED_ROOT))

from csn2api_runtime.credential_bundle import (  # noqa: E402
    create_credential_bundle,
    parse_credential_bundle,
)


class CredentialBundleTests(unittest.TestCase):
    def test_round_trip_uses_stable_cross_system_schema(self) -> None:
        bundle = create_credential_bundle({
            "oa": "SESSION=oa-value",
            "flight-portal": "JSESSIONID=ieb-value; iebJSid=browser-value",
        })

        self.assertEqual(bundle["format"], "csn2api-cookie-bundle")
        self.assertEqual(bundle["schemaVersion"], 1)
        self.assertEqual(
            parse_credential_bundle(bundle, allowed_system_ids={"flight-portal", "oa"}),
            {
                "flight-portal": "JSESSIONID=ieb-value; iebJSid=browser-value",
                "oa": "SESSION=oa-value",
            },
        )

    def test_rejects_unknown_duplicate_or_empty_systems(self) -> None:
        with self.assertRaisesRegex(ValueError, "未知系统"):
            parse_credential_bundle({
                "format": "csn2api-cookie-bundle",
                "schemaVersion": 1,
                "systems": [{"systemId": "unknown", "credentials": "secret=value"}],
            }, allowed_system_ids={"oa"})
        with self.assertRaisesRegex(ValueError, "重复"):
            parse_credential_bundle({
                "format": "csn2api-cookie-bundle",
                "schemaVersion": 1,
                "systems": [
                    {"systemId": "oa", "credentials": "a=1"},
                    {"systemId": "oa", "credentials": "a=2"},
                ],
            })


if __name__ == "__main__":
    unittest.main()
