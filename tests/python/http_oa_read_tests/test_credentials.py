from __future__ import annotations

import unittest

from .common import APP_ROOT  # noqa: F401
from http_oa_read.credentials import (
    credential_summary,
    parse_browser_headers,
    parse_credentials,
    parse_waiting_payload,
)


class CredentialTests(unittest.TestCase):
    def test_parses_all_cookie_pairs_from_header_without_values_in_summary(self) -> None:
        cookies = parse_credentials("Cookie: SESSION=secret-a; route=secret-b; flag=value=part")

        self.assertEqual(cookies, {"SESSION": "secret-a", "route": "secret-b", "flag": "value=part"})
        summary = credential_summary(cookies)
        self.assertEqual(summary, {"cookieCount": 3})
        self.assertNotIn("secret", str(summary))

    def test_parses_copy_as_curl_without_executing_it(self) -> None:
        source = (
            "curl 'https://work.csair.com/oai/work/login/userInfo' "
            "-H 'User-Agent: Browser/152 exact-profile' "
            "-H 'Cookie: SESSION=one; route=two' --data-raw 'ignored=true'"
        )
        cookies = parse_credentials(source)

        self.assertEqual(cookies, {"SESSION": "one", "route": "two"})
        self.assertEqual(parse_browser_headers(source), {"User-Agent": "Browser/152 exact-profile"})

    def test_browser_headers_only_accepts_user_agent_without_line_breaks(self) -> None:
        source = (
            "curl 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'Authorization: forbidden-secret' "
            "-H 'X-Requested-With: forged' "
            "-H 'User-Agent: Browser/152' "
            "-H 'Cookie: SESSION=one'"
        )

        self.assertEqual(parse_browser_headers(source), {"User-Agent": "Browser/152"})
        self.assertEqual(parse_browser_headers("Cookie: SESSION=one"), {})

    def test_parses_waiting_json_template_from_full_curl(self) -> None:
        source = (
            "curl --url 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'Cookie: SESSION=one' "
            "--data-raw '{\"moduleMainCategoryId\":-5,\"pageMode\":\"page\","
            "\"offsetPageIndex\":0,\"resultCountPerPage\":5}'"
        )

        self.assertEqual(
            parse_waiting_payload(source),
            {
                "moduleMainCategoryId": -5,
                "pageMode": "page",
                "offsetPageIndex": 0,
                "resultCountPerPage": 5,
            },
        )

    def test_ignores_json_body_from_other_curl_endpoint(self) -> None:
        source = (
            "curl 'https://work.csair.com/oai/doc/pc/form/sw/haveRead' "
            "-H 'Cookie: SESSION=one' --data-raw '{\"docId\":\"hidden\"}'"
        )

        self.assertIsNone(parse_waiting_payload(source))

    def test_rejects_missing_cookie_header(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cookie"):
            parse_credentials("curl https://work.csair.com/")


if __name__ == "__main__":
    unittest.main()
