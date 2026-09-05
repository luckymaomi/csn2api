from __future__ import annotations

import unittest

import requests

from .common import APP_ROOT  # noqa: F401
from http_oa_read.portal_client import (
    PortalBusinessError,
    PortalClient,
    PortalError,
    PortalSessionExpired,
)
from oa_protocol.client import DEFAULT_BROWSER_USER_AGENT
from oa_protocol.contract import parse_identity
from oa_protocol.models import WaitingRecord


class FakeResponse:
    def __init__(self, payload, status_code=200, url="https://work.csair.com/ok"):
        self.payload = payload
        self.status_code = status_code
        self.url = url
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self.payload


class FakeCookies:
    def __init__(self):
        self.values = {}

    def clear(self):
        self.values.clear()

    def set(self, name, value, **_kwargs):
        self.values[name] = value


class FakeSession:
    def __init__(self, get_responses=None, post_responses=None):
        self.headers = {}
        self.cookies = FakeCookies()
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        responses = self.get_responses if method == "GET" else self.post_responses
        return responses.pop(0)

    def close(self):
        self.closed = True


def row(index: int, category="DOC", subcategory="official-document"):
    return {
        "fileId": f"file-{index}",
        "fileTitle": f"测试公文 {index}",
        "fileTypeId": f"type-{index}",
        "stepItemId": f"step-{index}",
        "moduleMainCategoryCode": category,
        "moduleSubCategoryCode": subcategory,
        "moduleSubCategoryName": "测试模块",
    }


def page(rows, total):
    return FakeResponse(
        {
            "code": "200",
            "success": True,
            "message": "ok",
            "data": {"resultMyBoxItems": rows, "totalRecordCount": total},
        }
    )


def nested_page(rows, total):
    return FakeResponse(
        {
            "code": "200",
            "success": True,
            "data": {"page": {"resultMyBoxItems": rows, "totalRecordCount": str(total)}},
        }
    )


def user_info():
    return FakeResponse({
        "code": "200",
        "success": True,
        "data": {"loginUserInfo": {"empId": "900001", "empName": "测试用户"}},
    })


class PortalClientTests(unittest.TestCase):
    def test_parses_current_session_identity_from_user_info(self) -> None:
        self.assertEqual(
            parse_identity({"data": {"loginUserInfo": {"empId": "900001", "empName": "测试用户"}}}),
            {"staffNumber": "900001", "name": "测试用户"},
        )
        with self.assertRaisesRegex(PortalError, "当前登录人"):
            parse_identity({"data": {}})

    def test_verify_requires_business_success_and_keeps_cookie_values_private(self) -> None:
        session = FakeSession(get_responses=[user_info()])
        client = PortalClient(session_factory=lambda: session)

        result = client.load_credentials("Cookie: SESSION=secret; route=private")

        self.assertEqual(result["cookieCount"], 2)
        self.assertNotIn("secret", str(result))
        self.assertEqual(session.cookies.values, {"SESSION": "secret", "route": "private"})

    def test_verify_reuses_browser_user_agent_from_full_curl(self) -> None:
        session = FakeSession(get_responses=[user_info()])
        client = PortalClient(session_factory=lambda: session)

        client.load_credentials(
            "curl 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'User-Agent: Browser/152 exact-profile' "
            "-H 'Cookie: SESSION=secret'"
        )

        self.assertEqual(session.headers["User-Agent"], "Browser/152 exact-profile")

    def test_verify_uses_default_browser_user_agent_for_cookie_only_credentials(self) -> None:
        session = FakeSession(get_responses=[user_info()])
        client = PortalClient(session_factory=lambda: session)

        client.load_credentials("Cookie: SESSION=secret")

        self.assertEqual(session.headers["User-Agent"], DEFAULT_BROWSER_USER_AGENT)

    def test_verify_rejects_expired_business_code_even_on_http_200(self) -> None:
        session = FakeSession(get_responses=[FakeResponse({"code": "301", "message": "expired"})])
        client = PortalClient(session_factory=lambda: session)

        with self.assertRaises(PortalSessionExpired):
            client.load_credentials("Cookie: SESSION=secret")

    def test_verify_does_not_follow_sso_redirect(self) -> None:
        session = FakeSession(get_responses=[FakeResponse({}, status_code=302)])
        client = PortalClient(session_factory=lambda: session)

        with self.assertRaisesRegex(PortalSessionExpired, "query/waiting"):
            client.load_credentials("Cookie: SESSION=secret")

        self.assertFalse(session.calls[0][2]["allow_redirects"])
        self.assertTrue(session.closed)

    def test_verify_reports_timeout_and_closes_candidate_session(self) -> None:
        class TimeoutSession(FakeSession):
            def request(self, method, url, **kwargs):
                self.calls.append((method, url, kwargs))
                raise requests.Timeout("timed out")

        session = TimeoutSession()
        client = PortalClient(session_factory=lambda: session)

        with self.assertRaisesRegex(PortalError, "超时"):
            client.load_credentials("Cookie: SESSION=secret")

        self.assertTrue(session.closed)
        self.assertEqual(session.calls[0][2]["timeout"], (5, 10))

    def test_scan_uses_json_zero_based_pages_and_classifies_records(self) -> None:
        first_rows = [row(index) for index in range(100)]
        last_row = row(100, "WORKFLOW_PLATFORM", "DI")
        session = FakeSession(
            get_responses=[user_info()],
            post_responses=[page(first_rows, 101), page([last_row], 101)],
        )
        client = PortalClient(session_factory=lambda: session)
        client.load_credentials("Cookie: SESSION=secret")

        snapshot = client.scan_waiting()

        self.assertEqual(snapshot.total, 101)
        self.assertEqual(snapshot.eligible_count, 100)
        self.assertEqual(snapshot.skipped_count, 1)
        post_calls = [call for call in session.calls if call[0] == "POST"]
        self.assertEqual(post_calls[0][2]["json"]["offsetPageIndex"], 0)
        self.assertEqual(post_calls[1][2]["json"]["offsetPageIndex"], 1)
        self.assertEqual(post_calls[0][2]["json"]["resultCountPerPage"], 100)

    def test_scan_reuses_waiting_curl_template_and_accepts_nested_page_contract(self) -> None:
        session = FakeSession(
            get_responses=[user_info()],
            post_responses=[nested_page([row(1)], 1)],
        )
        client = PortalClient(session_factory=lambda: session)
        client.load_credentials(
            "curl 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'Cookie: SESSION=secret' "
            "--data-raw '{\"moduleMainCategoryId\":-5,\"pageMode\":\"page\","
            "\"offsetPageIndex\":0,\"resultCountPerPage\":5}'"
        )

        snapshot = client.scan_waiting()

        self.assertEqual(snapshot.total, 1)
        request_body = session.calls[-1][2]["json"]
        self.assertEqual(request_body["offsetPageIndex"], 0)
        self.assertEqual(request_body["resultCountPerPage"], 100)
        self.assertNotIn("moduleMainCategoryId", request_body)
        self.assertNotIn("fileTitle", request_body)

    def test_mark_read_posts_confirmed_mapping_once_without_followup_query(self) -> None:
        record = WaitingRecord.from_payload(row(1))
        session = FakeSession(
            get_responses=[user_info()],
            post_responses=[FakeResponse({"code": "200", "data": None, "message": "ok"})],
        )
        client = PortalClient(session_factory=lambda: session)
        client.load_credentials("Cookie: SESSION=secret")

        client.mark_read(record)

        have_read_call = [call for call in session.calls if call[1].endswith("/haveRead")]
        self.assertEqual(len(have_read_call), 1)
        self.assertEqual(
            have_read_call[0][2]["json"],
            {
                "approveOpinionType": None,
                "approveOpinionContent": None,
                "docId": "file-1",
                "docType": "type-1",
                "flowStepId": "step-1",
            },
        )
        verify_calls = [call for call in session.calls if call[1].endswith("/query/waiting")]
        self.assertEqual(verify_calls, [])

    def test_mark_read_raises_on_business_failure(self) -> None:
        record = WaitingRecord.from_payload(row(1))
        session = FakeSession(
            get_responses=[user_info()],
            post_responses=[FakeResponse({"code": "500", "message": "failed"})],
        )
        client = PortalClient(session_factory=lambda: session)
        client.load_credentials("Cookie: SESSION=secret")

        with self.assertRaises(PortalBusinessError):
            client.mark_read(record)


if __name__ == "__main__":
    unittest.main()
