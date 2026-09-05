import unittest
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "http-soc-positioning-helper"
SHARED_ROOT = Path(__file__).resolve().parents[3] / "public" / "tool" / "app" / "_shared"
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(SHARED_ROOT))

from soc_protocol import FlightOption, StaffIdentity  # noqa: E402
from soc_protocol.client import DEFAULT_BROWSER_USER_AGENT  # noqa: E402
from soc_positioning.portal_client import SocPortalClient  # noqa: E402


class FakeResponse:
    status_code = 200
    headers: dict[str, str] = {}
    reason = "OK"
    url = "https://soc.example.test/"

    def __init__(self, text: str = "", payload: object | None = None):
        self.text = text
        self.payload = payload

    def json(self):
        if self.payload is None:
            raise ValueError("not json")
        return self.payload

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.cookies = {}
        self.posts: list[tuple[str, object]] = []
        self.submit_payload: object = {"message": "录入成功！"}

    def get(self, _url, **_kwargs):
        return FakeResponse("<form id='applyFm'><input name='KkTvlApply'></form>")

    def request(self, method, url, **kwargs):
        if method == "GET":
            return self.get(url, **kwargs)
        data = kwargs.pop("data", None)
        return self.post(url, data=data, **kwargs)

    def post(self, url, data=None, **_kwargs):
        self.posts.append((url, data))
        if url.endswith("getFltNumList.action"):
            return FakeResponse(payload={"rows": [{
                "fltNr": "1234", "seqNr": "01", "fltDt": "2026-01-15",
                "fltRoute": "CANCSX", "fltTime": "0800-1000", "crewDepDt": "2026-01-15 07:00",
                "subfleetType": "32A", "alnCd": "CZ",
            }], "total": 1})
        if url.endswith("getStaffValidate.action"):
            return FakeResponse(payload={"failFeedback": "", "rows": [{"staffNum": "000001", "chnName": "测试员工"}]})
        if url.endswith("getStaffMobile.action"):
            return FakeResponse(payload={"staffMobile": ""})
        if url.endswith("addKkTvlApply.action"):
            return FakeResponse(payload=self.submit_payload)
        return FakeResponse(payload={})


class SocPortalClientTests(unittest.TestCase):
    def test_request_headers_use_default_browser_user_agent(self):
        client = SocPortalClient(session=FakeSession())

        self.assertEqual(client.protocol.headers()["User-Agent"], DEFAULT_BROWSER_USER_AGENT)

    def test_parses_only_server_rendered_login_name(self):
        identity = SocPortalClient._parse_identity(
            "<div id='checkout_soc'>欢迎您，测试用户 <span>员工号：900001</span><a>退出</a></div>"
        )
        self.assertEqual(identity, {"name": "测试用户"})

    def test_keeps_dynamic_option_value_and_matches_display_number(self):
        session = FakeSession()
        client = SocPortalClient(session=session)
        client.load_credentials("JSESSIONID=session-value")
        options = client.list_flights("2026-01-15", "广州", "长沙")
        self.assertEqual(options[0].value, "1234,01,2026-01-15,CANCSX,0800-1000,2026-01-15 07:00,32A,CZ")
        self.assertEqual(client.choose_flight(options, "CZ1234"), options[0])

    def test_matches_flight_number_when_soc_appends_schedule_to_flt_nr(self):
        option = FlightOption(
            "OQ2308 (19:55-23:00)(49/176)32X", "2308 (19:55-23:00)", "02",
            "2026-08-25", "PVGCKG", "19:55-23:00", "", "32X", "OQ", "composite",
        )
        self.assertTrue(SocPortalClient._flight_match(option, "OQ2308"))
        self.assertTrue(SocPortalClient._flight_match(option, "2308"))
        self.assertFalse(SocPortalClient._flight_match(option, "230"))
        self.assertEqual(SocPortalClient().choose_flight([option], "OQ2308"), option)

    def test_business_success_requires_exact_message(self):
        session = FakeSession()
        client = SocPortalClient(session=session)
        record = {
            "员工号": "000001", "航班日期": "2026-01-15", "出发地": "广州", "目的地": "长沙",
            "申请原因代码": "6", "备注": "示例备注",
        }
        option = FlightOption("CZ1234", "1234", "01", "2026-01-15", "CANCSX", "0800-1000", "", "32A", "CZ", "composite")
        identity = StaffIdentity("000001", "测试员工", "")
        client.load_credentials("JSESSIONID=session-value")
        self.assertTrue(client.submit(record, option, identity).success)
        session.submit_payload = {"message": "业务校验失败"}
        self.assertFalse(client.submit(record, option, identity).success)


if __name__ == "__main__":
    unittest.main()
