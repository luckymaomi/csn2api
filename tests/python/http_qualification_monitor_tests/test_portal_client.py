from __future__ import annotations

import copy
import json
import unittest

try:
    from .common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # type: ignore[no-redef]  # noqa: F401
from http_qualification_monitor.portal_client import (
    PortalClient,
    PortalSessionExpired,
)
from ieb_protocol import format_credentials
from ieb_protocol import IebContractError
from ieb_protocol.base import parse_current_identity
from ieb_protocol.qualification_monitor import EXPORT_PATH
from ieb_protocol.qualification_monitor_contract import build_filter_params, parse_classification_tree, validate_ooxml


HOME_HTML = """
<div id="personalInfo"><span class="name-txt">测试用户</span></div>
<div class="detailInfo"><div class="empid"><span title="900001"></span></div></div>
"""


class FakeCookies:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def clear(self) -> None:
        self.values.clear()

    def set(self, name: str, value: str, **_kwargs: object) -> None:
        self.values[name] = value


class FakeResponse:
    def __init__(self, *, payload: object | None = None, content: bytes = b"", url: str = "https://ieb.csair.com/ok") -> None:
        self._payload = payload
        self.content = content
        self.url = url
        self.status_code = 200
        self.text = content.decode("utf-8", errors="ignore")

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        if self._payload is None:
            raise json.JSONDecodeError("invalid", "", 0)
        return self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = FakeCookies()
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.assert_get(method)
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    @staticmethod
    def assert_get(method: str) -> None:
        if method != "GET":
            raise AssertionError(f"unexpected method: {method}")

    def close(self) -> None:
        return None


class PortalClientTests(unittest.TestCase):
    def test_parses_current_session_identity_from_home_page(self) -> None:
        self.assertEqual(
            parse_current_identity(HOME_HTML, 200),
            {"staffNumber": "900001", "name": "测试用户"},
        )
        with self.assertRaisesRegex(IebContractError, "当前登录人"):
            parse_current_identity("<html></html>", 200)

    def test_parses_three_expected_parents_in_portal_order(self) -> None:
        groups = parse_classification_tree(CLASSIFICATION_PAYLOAD)
        self.assertEqual([group.code for group in groups], ["ZZYX", "ZZZG", "ZZTS"])
        self.assertEqual([item.code for group in groups for item in group.items], ["90D3F", "120D100H", "ICAO4", "ZZJLQL"])

    def test_rejects_duplicates_missing_names_and_unexpected_parents(self) -> None:
        duplicate = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        duplicate[1]["sonList"][0]["msgCode"] = "90D3F"
        with self.assertRaises(IebContractError):
            parse_classification_tree(duplicate)
        missing_name = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        missing_name[0]["sonList"][0]["msgType"] = ""
        with self.assertRaises(IebContractError):
            parse_classification_tree(missing_name)
        unexpected = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        unexpected.append({"msgType": "未知", "msgCode": "OTHER", "sonList": []})
        with self.assertRaises(IebContractError):
            parse_classification_tree(unexpected)

    def test_export_params_keep_empty_filters_and_never_add_pagination(self) -> None:
        params = build_filter_params("90D3F")
        self.assertIn(("qualType", "90D3F"), params)
        self.assertIn(("staffNum", ""), params)
        self.assertIn(("effectiveModel", ""), params)
        names = [name for name, _value in params]
        self.assertNotIn("pageNum", names)
        self.assertNotIn("pageSize", names)

    def test_validates_required_ooxml_parts(self) -> None:
        payload = ooxml_bytes()
        self.assertIs(validate_ooxml(payload), payload)
        with self.assertRaises(IebContractError):
            validate_ooxml(b"<html>login</html>")

    def test_verify_and_export_use_get_and_preserve_native_bytes(self) -> None:
        native = ooxml_bytes("native")
        session = FakeSession([
            FakeResponse(payload=CLASSIFICATION_PAYLOAD),
            FakeResponse(content=HOME_HTML.encode("utf-8")),
            FakeResponse(content=native),
        ])
        client = PortalClient(session=session)
        summary, groups = client.load_credentials("JSESSIONID=a; iebJSid=b")
        self.assertEqual(client.copyable_credentials, format_credentials({"JSESSIONID": "a", "iebJSid": "b"}))
        exported = client.export_qualification(groups[0].items[0].code)

        self.assertEqual(summary["qualificationCount"], 4)
        self.assertEqual(summary["identity"], {"staffNumber": "900001", "name": "测试用户"})
        self.assertTrue(session.calls[1][0].endswith("/index/index"))
        self.assertEqual(session.calls[1][1]["headers"]["Accept"], "text/html,application/xhtml+xml")
        self.assertEqual(exported, native)
        self.assertTrue(session.calls[-1][0].endswith(EXPORT_PATH))
        self.assertEqual(session.calls[-1][1]["params"], build_filter_params("90D3F"))

    def test_login_redirect_clears_verified_state(self) -> None:
        session = FakeSession([FakeResponse(payload=[], url="https://ieb.csair.com/login")])
        client = PortalClient(session=session)
        with self.assertRaises(PortalSessionExpired):
            client.load_credentials("JSESSIONID=a; iebJSid=b")
        self.assertFalse(client.verified)


if __name__ == "__main__":
    unittest.main()
