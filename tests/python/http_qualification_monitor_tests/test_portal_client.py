from __future__ import annotations

import copy
import io
import json
import unittest
import zipfile

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
from ieb_protocol.qualification_monitor import (
    ALARM_EXPORT_PATH,
    INSPECTOR_EXPORT_PATH,
    INSPECTOR_QUERY_PATH,
)
from ieb_protocol.qualification_monitor_contract import (
    build_filter_params,
    build_inspector_filter_params,
    build_inspector_query_params,
    parse_classification_tree,
    validate_ooxml,
)


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

    def test_verify_metadata_and_export_are_separate_get_stages(self) -> None:
        native = ooxml_bytes("native")
        session = FakeSession([
            FakeResponse(content=HOME_HTML.encode("utf-8")),
            FakeResponse(content=HOME_HTML.encode("utf-8")),
            FakeResponse(payload=CLASSIFICATION_PAYLOAD),
            FakeResponse(content=native),
        ])
        client = PortalClient(session=session)
        summary = client.load_credentials("JSESSIONID=a; iebJSid=b")
        self.assertEqual(len(session.calls), 1)
        client.check_session()
        self.assertTrue(session.calls[1][0].endswith("/index/index"))
        groups = client.load_metadata()
        self.assertEqual(client.copyable_credentials, format_credentials({"JSESSIONID": "a", "iebJSid": "b"}))
        exported = client.export_qualification(groups[0].items[0].code)

        self.assertEqual(summary["identity"], {"staffNumber": "900001", "name": "测试用户"})
        self.assertTrue(session.calls[0][0].endswith("/index/index"))
        self.assertEqual(session.calls[0][1]["headers"]["Accept"], "text/html,application/xhtml+xml")
        self.assertEqual(exported, native)
        self.assertTrue(session.calls[-1][0].endswith(ALARM_EXPORT_PATH))
        self.assertEqual(session.calls[-1][1]["params"], build_filter_params("90D3F"))

    def test_inspector_library_uses_dedicated_query_and_export_contracts(self) -> None:
        page = {
            "list": [{"staffNum": "900001", "personName": "测试用户", "checkerType": "PCC"}],
            "total": 36,
            "pages": 2,
            "pageNum": 2,
            "pageSize": 20,
            "hasNextPage": False,
        }
        native = ooxml_bytes("inspector")
        session = FakeSession([
            FakeResponse(payload=page),
            FakeResponse(content=native),
        ])
        client = PortalClient(session=session)
        client.ieb.load_credentials("JSESSIONID=a; iebJSid=b")

        _response, result = client.protocol.request_page(
            "JCY", {"staffNumArr": "900001", "checkerType": "PCC"}, 2, 20,
        )
        _export_response, exported = client.protocol.request_export("JCY", {"checkerType": "PCC"})

        self.assertEqual((result.total, result.pages), (36, 2))
        self.assertEqual(exported, native)
        self.assertTrue(session.calls[0][0].endswith(INSPECTOR_QUERY_PATH))
        self.assertEqual(
            session.calls[0][1]["params"],
            build_inspector_query_params({"staffNumArr": "900001", "checkerType": "PCC"}, 2, 20),
        )
        self.assertTrue(session.calls[1][0].endswith(INSPECTOR_EXPORT_PATH))
        self.assertEqual(session.calls[1][1]["params"], build_inspector_filter_params({"checkerType": "PCC"}))

    def test_inspector_export_uses_all_query_pages_when_native_export_is_unavailable(self) -> None:
        first = {
            "list": [
                {"staffNum": "900001", "personName": "测试用户", "checkerType": "PCC", "gradeNo": None},
            ],
            "total": 2,
            "pages": 2,
            "pageNum": 1,
            "pageSize": 1,
            "hasNextPage": True,
        }
        second = {
            "list": [
                {"staffNum": "900002", "personName": "测试用户二", "checkerType": "ATE", "remark": "备注"},
            ],
            "total": 2,
            "pages": 2,
            "pageNum": 2,
            "pageSize": 1,
            "hasNextPage": False,
        }
        session = FakeSession([FakeResponse(payload=first), FakeResponse(payload=second)])
        client = PortalClient(session=session)
        client.ieb.load_credentials("JSESSIONID=a; iebJSid=b")

        exported = client.export_qualification("JCY")

        self.assertTrue(exported.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("staffNum", worksheet)
        self.assertIn("900001", worksheet)
        self.assertIn("900002", worksheet)
        self.assertIn("备注", worksheet)
        self.assertEqual(len(session.calls), 2)
        self.assertTrue(all(call[0].endswith(INSPECTOR_QUERY_PATH) for call in session.calls))

    def test_request_all_pages_accepts_a_single_page_result(self) -> None:
        page = {
            "list": [{"staffNum": "900001"}],
            "total": 1,
            "pages": 1,
            "pageNum": 1,
            "pageSize": 20,
            "hasNextPage": False,
        }
        session = FakeSession([FakeResponse(payload=page)])
        client = PortalClient(session=session)
        client.ieb.load_credentials("JSESSIONID=a; iebJSid=b")

        pages = client.protocol.request_all_pages("JCY")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].rows[0]["staffNum"], "900001")

    def test_login_redirect_clears_verified_state(self) -> None:
        session = FakeSession([FakeResponse(payload=[], url="https://ieb.csair.com/login")])
        client = PortalClient(session=session)
        with self.assertRaises(PortalSessionExpired):
            client.load_credentials("JSESSIONID=a; iebJSid=b")
        self.assertFalse(client.verified)


if __name__ == "__main__":
    unittest.main()
