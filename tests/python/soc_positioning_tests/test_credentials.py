import unittest
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-soc-positioning-helper"
SHARED_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "_shared"
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(SHARED_ROOT))

from soc_protocol import format_credentials, parse_credentials  # noqa: E402


class SocCredentialTests(unittest.TestCase):
    def test_parses_cookie_header_from_curl_without_executing_command(self):
        source = "curl 'https://soc.example.test/page' -H 'Cookie: JSESSIONID=session-value; com.trs.idm.coSessionId=id-value'"
        cookies = parse_credentials(source)
        self.assertEqual(cookies, {
            "JSESSIONID": "session-value",
            "com.trs.idm.coSessionId": "id-value",
        })
        self.assertEqual(format_credentials(cookies), "JSESSIONID=session-value; com.trs.idm.coSessionId=id-value")

    def test_requires_jsessionid(self):
        with self.assertRaisesRegex(ValueError, "JSESSIONID"):
            parse_credentials("Cookie: tracking=value")


if __name__ == "__main__":
    unittest.main()
