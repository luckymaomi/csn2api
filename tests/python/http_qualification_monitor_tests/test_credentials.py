from __future__ import annotations

import unittest

try:
    from .common import APP_ROOT  # noqa: F401
except ImportError:
    from common import APP_ROOT  # type: ignore[no-redef]  # noqa: F401
from http_qualification_monitor.credentials import parse_credentials


class CredentialTests(unittest.TestCase):
    def test_accepts_cookie_header_and_text_curl_without_executing_it(self) -> None:
        self.assertEqual(
            parse_credentials("Cookie: JSESSIONID=session; iebJSid=browser; ignored=value"),
            {"JSESSIONID": "session", "iebJSid": "browser", "ignored": "value"},
        )
        self.assertEqual(
            parse_credentials("curl 'https://ieb.csair.com/a' -H 'Cookie: JSESSIONID=a; iebJSid=b'"),
            {"JSESSIONID": "a", "iebJSid": "b"},
        )

    def test_requires_both_session_cookies(self) -> None:
        with self.assertRaisesRegex(ValueError, "iebJSid"):
            parse_credentials("JSESSIONID=only")


if __name__ == "__main__":
    unittest.main()
