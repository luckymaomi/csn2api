from __future__ import annotations

import copy
import json
import unittest

try:
    from .common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # noqa: F401
except ImportError:
    from common import APP_ROOT, CLASSIFICATION_PAYLOAD, ooxml_bytes  # type: ignore[no-redef]  # noqa: F401
from http_qualification_monitor.portal_client import (
    EXPORT_PATH,
    PortalClient,
    PortalError,
    PortalSessionExpired,
    build_export_params,
    parse_classification_tree,
    validate_ooxml,
)


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

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def close(self) -> None:
        return None


class PortalClientTests(unittest.TestCase):
    def test_parses_three_expected_parents_in_portal_order(self) -> None:
        groups = parse_classification_tree(CLASSIFICATION_PAYLOAD)
        self.assertEqual([group.code for group in groups], ["ZZYX", "ZZZG", "ZZTS"])
        self.assertEqual([item.code for group in groups for item in group.items], ["90D3F", "120D100H", "ICAO4", "ZZJLQL"])

    def test_rejects_duplicates_missing_names_and_unexpected_parents(self) -> None:
        duplicate = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        duplicate[1]["sonList"][0]["msgCode"] = "90D3F"
        with self.assertRaises(PortalError):
            parse_classification_tree(duplicate)
        missing_name = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        missing_name[0]["sonList"][0]["msgType"] = ""
        with self.assertRaises(PortalError):
            parse_classification_tree(missing_name)
        unexpected = copy.deepcopy(CLASSIFICATION_PAYLOAD)
        unexpected.append({"msgType": "未知", "msgCode": "OTHER", "sonList": []})
        with self.assertRaises(PortalError):
            parse_classification_tree(unexpected)

    def test_export_params_keep_empty_filters_and_never_add_pagination(self) -> None:
        params = build_export_params("90D3F")
        self.assertEqual(params["qualType"], "90D3F")
        self.assertEqual(params["staffNum"], "")
        self.assertEqual(params["effectiveModel"], "")
        self.assertNotIn("pageNum", params)
        self.assertNotIn("pageSize", params)

    def test_validates_required_ooxml_parts(self) -> None:
        payload = ooxml_bytes()
        self.assertIs(validate_ooxml(payload), payload)
        with self.assertRaises(PortalError):
            validate_ooxml(b"<html>login</html>")

    def test_verify_and_export_use_get_and_preserve_native_bytes(self) -> None:
        native = ooxml_bytes("native")
        session = FakeSession([
            FakeResponse(payload=CLASSIFICATION_PAYLOAD),
            FakeResponse(content=native),
        ])
        client = PortalClient(session=session)
        summary, groups = client.load_credentials("JSESSIONID=a; iebJSid=b")
        exported = client.export_qualification(groups[0].items[0].code)

        self.assertEqual(summary["qualificationCount"], 4)
        self.assertEqual(exported, native)
        self.assertTrue(session.calls[-1][0].endswith(EXPORT_PATH))
        self.assertEqual(session.calls[-1][1]["params"], build_export_params("90D3F"))

    def test_login_redirect_clears_verified_state(self) -> None:
        session = FakeSession([FakeResponse(payload=[], url="https://ieb.csair.com/login")])
        client = PortalClient(session=session)
        with self.assertRaises(PortalSessionExpired):
            client.load_credentials("JSESSIONID=a; iebJSid=b")
        self.assertFalse(client.verified)


if __name__ == "__main__":
    unittest.main()
