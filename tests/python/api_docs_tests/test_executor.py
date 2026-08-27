from __future__ import annotations

import io
import json
import re
import threading
import unittest
import zipfile
from collections import deque

from openpyxl import Workbook

from .common import CATALOG_ROOT
from api_docs.catalog import ApiCatalog
from api_docs.executor import ApiExecutor
from api_docs.systems.flight_portal import random_keepalive_interval


QUERY_PAGE_HTML = """
<form id="showflyTimeExperienceQueryForm" action="/newieb/flytime/showFlytimeManyQueryList"></form>
"""

IEB_HOME_HTML = """
<div id="personalInfo"><span class="name-txt">测试人员</span></div>
<div class="detailInfo"><div class="empid"><span title="900001"></span></div></div>
"""

SOC_NAVIGATION_HTML = """
<div id="checkout_soc">欢迎您，测试用户 <span>员工号：900001</span><a>退出</a></div>
"""

SOC_ENTRY_HTML = """
<form id="applyFm"><input name="KkTvlApply"></form>
"""

ENTRY_HTML = """
<div id="showNonproductionTaskImportPage">
  <form id="nonproductionTaskImportForm">
    <select id="lockType">
      <option value=""></option>
      <option value="BS_STUDY" class="0" id="0">【BS_STUDY】业务学习</option>
      <option value="RECU_LVE" class="1" id="1">【RECU_LVE】健康疗养</option>
    </select>
  </form>
</div>
"""

FLIGHT_RESULT_HTML = """
<table>
  <thead><tr><th>员工号</th><th>姓名</th><th>飞行时间</th><th>起落总数</th></tr></thead>
  <tbody><tr><td>900001</td><td>测试人员</td><td>12:30</td><td>8</td></tr></tbody>
</table>
"""

LOCK_RESULT_HTML = """
<div id="showNonproductionTaskImportResultPage1">
  <div class="hDiv"><table><thead><tr><th>锁班状态</th><th>员工号</th><th>锁班类型</th></tr></thead></table></div>
  <div class="bDiv"><table><tbody class="list"><tr><td>待审批</td><td>900001</td><td>BS_STUDY</td></tr></tbody></table></div>
</div>
<div id="showNonproductionTaskImportResultPage2">
  <div class="hDiv"><table><thead><tr><th>锁班结果</th><th>冲突说明</th></tr></thead></table></div>
  <div class="bDiv"><table><tbody class="list"><tr><td colspan="2">没有相关信息</td></tr></tbody></table></div>
</div>
"""

LOCK_RESULT_TABLE_ONLY_HTML = LOCK_RESULT_HTML.replace(
    'id="showNonproductionTaskImportResultPage1"',
    'id="showNonproductionTaskImportResultPage1table"',
)

BASIC_INFO_JSON = json.dumps({
    "empDto": {"birthDate": "2000-01-01", "position": "飞行员"},
    "eduList": [{"school": "样例院校", "education": "本科"}],
    "workList": [],
    "titleList": [],
    "relationList": [],
}, ensure_ascii=False)

TECHNICAL_RESULT_HTML = """
<div id="qualList">
  <table><tr><th>#</th><th>技术等级代码</th><th>技术等级</th><th>水平等级</th><th>机型</th><th>生效时间</th><th>失效时间</th><th>对应检查记录</th><th>数据来源</th></tr></table>
  <table><tbody><tr><td>1</td><td>CAP</td><td>机长</td><td>一级</td><td>A320</td><td>2025-01-01</td><td>2026-01-01</td><td>检查记录</td><td>门户</td></tr></tbody></table>
</div>
"""

QUALIFICATION_PAGE_INFO = json.dumps({
    "list": [
        {"staffNum": "900001", "name": "测试人员", "alarmType": "2"},
        {"staffNum": "900002", "name": "样例人员", "specialField": "动态字段"},
    ],
    "total": 42,
    "pages": 3,
    "pageNum": 2,
    "pageSize": 20,
    "hasNextPage": True,
}, ensure_ascii=False)

ROSTER_FILTER_HTML = """
<form id="showEmpProfileCompositeListPageForm">
  <select name="primaryBaseArray"><option value="">全部注册基地</option></select>
  <select name="baseArray"><option value="">全部运行基地</option></select>
  <select name="techBase"><option value="">全部技术基地</option></select>
  <select name="fleetCdToArray" multiple><option value="777">B777</option><option value="787">B787</option></select>
  <select name="bolMultiQualCd"><option value="">全部混飞状态</option></select>
  <select name="qualTypeArray" multiple><option value="">全部技术等级</option></select>
  <select name="bolPriBase"><option value="">全部帮飞状态</option></select>
  <select name="bolJCY"><option value="">全部教员状态</option></select>
  <select name="activeStatusArray" multiple><option value="ZAIZHI">在职</option></select>
  <select name="fleetCdbranch"><option value="">全部分部</option></select>
</form>
"""

ROSTER_QUALIFICATION_HTML = """
<table><tbody><tr>
  <td><input type="checkbox" value="internal-id"></td>
  <td class="qualCdTd" data-qualCd="RAMA">RAMA</td>
  <td>北美区域单飞资格</td><td>RAMA</td><td>QYHXZG</td><td>区域航线资格</td>
</tr></tbody></table>
"""


def make_roster_export() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["员工号", "姓名", "运行资格"])
    sheet.append([900001, "测试人员", "RAMA"])
    sheet.append(["090002", "样例人员", "RAMA"])
    source = io.BytesIO()
    workbook.save(source)
    workbook.close()

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source.getvalue())) as archive, zipfile.ZipFile(output, "w") as rewritten:
        for item in archive.infolist():
            data = archive.read(item.filename)
            if item.filename.startswith("xl/worksheets/") and item.filename.endswith(".xml"):
                data = re.sub(br'<dimension ref="[^"]+"', b'<dimension ref="A1"', data, count=1)
            rewritten.writestr(item, data)
    return output.getvalue()


CAAC_LIST = json.dumps({"total": 2, "rows": [{"pilotId": "sample-1", "pilotname": "样例人员"}]}, ensure_ascii=False)
CAAC_NAME_LIST = json.dumps({
    "total": 1,
    "rows": [{"pilotId": "sample-1", "pilotname": "样例人员", "archiveNo": "00000001"}],
}, ensure_ascii=False)
CAAC_DETAIL = json.dumps({
    "pilotId": "sample-1",
    "pilotname": "样例人员",
    "archiveNo": "00000001",
    "layerInfosList": [{"layerinfo": "航线运输驾驶员", "sublayers": []}],
    "educationList": [{"school": "样例院校", "degree": "本科"}],
}, ensure_ascii=False)

OA_USER_INFO = json.dumps({"code": 200, "data": {"loginUserInfo": {"empId": "900001", "empName": "示例用户"}}}, ensure_ascii=False)
OA_WAITING = json.dumps({
    "code": 200,
    "data": {
        "resultMyBoxItems": [
            {
                "fileId": "doc-1",
                "fileTitle": "示例公文一",
                "fileTypeId": "type-1",
                "stepItemId": "step-1",
                "moduleMainCategoryCode": "DOC",
                "moduleSubCategoryCode": "official-document",
                "moduleSubCategoryName": "公文",
            },
            {
                "fileId": "other-1",
                "fileTitle": "示例异类待办",
                "fileTypeId": "other-type",
                "stepItemId": "other-step",
                "moduleMainCategoryCode": "OTHER",
                "moduleSubCategoryCode": "workflow",
                "moduleSubCategoryName": "其他流程",
            },
            {
                "fileId": "doc-2",
                "fileTitle": "示例公文二",
                "fileTypeId": "type-2",
                "stepItemId": "step-2",
                "moduleMainCategoryCode": "DOC",
                "moduleSubCategoryCode": "official-document",
                "moduleSubCategoryName": "公文",
            },
        ],
        "totalRecordCount": 3,
    },
}, ensure_ascii=False)
OA_SUCCESS = json.dumps({"code": 200, "message": "ok"}, ensure_ascii=False)
OA_FAILURE = json.dumps({"code": 500, "message": "failed"}, ensure_ascii=False)


class FakeCookies:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name: str, value: str, **_options: object) -> None:
        self.values[name] = value

    def update(self, values: dict[str, str]) -> None:
        self.values.update(values)


class FakeResponse:
    def __init__(
        self,
        text: str,
        url: str = "https://ieb.example.test/result",
        content_type: str = "text/html; charset=utf-8",
        content: bytes | None = None,
    ) -> None:
        self.text = text
        self.content = content if content is not None else text.encode("utf-8")
        self.url = url
        self.status_code = 200
        self.reason = "OK"
        self.headers = {"Content-Type": content_type, "Set-Cookie": "secret=value"}

    def json(self) -> object:
        return json.loads(self.text)


class FakeSession:
    def __init__(self, responses: list[FakeResponse], request_event: threading.Event | None = None) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = FakeCookies()
        self.responses = deque(responses)
        self.requests: list[dict[str, object]] = []
        self.closed = False
        self.request_event = request_event

    def request(self, *args: object, **kwargs: object) -> FakeResponse:
        if args:
            kwargs = {"method": args[0], "url": args[1], **kwargs}
        self.requests.append(kwargs)
        if self.request_event is not None and len(self.requests) > 1:
            self.request_event.set()
        return self.responses.popleft()

    def close(self) -> None:
        self.closed = True


class ExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ApiCatalog(CATALOG_ROOT)

    def create_executor(
        self,
        responses: list[FakeResponse],
        *,
        keepalive_interval: int = 60,
        request_event: threading.Event | None = None,
    ) -> tuple[ApiExecutor, FakeSession]:
        session = FakeSession(responses, request_event)
        executor = ApiExecutor(
            self.catalog,
            session_factory=lambda: session,
            keepalive_interval_factory=lambda: keepalive_interval,
        )
        self.addCleanup(executor.close)
        return executor, session

    def test_cookie_validation_does_not_load_lock_types(self) -> None:
        executor, session = self.create_executor([FakeResponse(QUERY_PAGE_HTML), FakeResponse(IEB_HOME_HTML), FakeResponse(ENTRY_HTML)])
        result = executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        self.assertTrue(result["ready"])
        self.assertEqual(result["identity"], {"staffNumber": "900001", "name": "测试人员"})
        self.assertEqual(
            result["credentials"],
            "JSESSIONID=session-value; iebJSid=browser-value",
        )
        self.assertNotIn("credentials", executor.session_status())
        self.assertNotIn("lockTypeCount", result)
        self.assertEqual(len(session.requests), 2)
        self.assertEqual(
            session.requests[0]["url"],
            self.catalog.get_session_request("flight-portal", "validation").url,
        )

        options = executor.load_options("lock-types")
        self.assertEqual(len(session.requests), 3)
        self.assertEqual(options[0]["value"], "BS_STUDY")
        self.assertEqual(
            session.requests[2]["url"],
            self.catalog.get_option_source("lock-types").url,
        )

    def test_caac_session_is_independent_and_kept_alive(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(CAAC_LIST, url="https://fsop.example.test/list", content_type="application/json"),
            FakeResponse(CAAC_LIST, url="https://fsop.example.test/list", content_type="application/json"),
        ])
        loaded = executor.load_credentials(
            r"yzzzm=a; JSESSIONID=session\u0021route; home=h\_1",
            "caac-fsop",
        )
        self.assertTrue(loaded["ready"])
        self.assertIsNone(loaded["identity"])
        self.assertTrue(loaded["keepAlive"]["running"])
        self.assertEqual(session.cookies.values["JSESSIONID"], "session!route")
        result = executor.execute("caac-pilot-export.pilot-list", {"page": "1", "rows": "10"})
        self.assertEqual(result["data"]["summary"]["total"], 2)
        self.assertEqual(result["data"]["summary"]["recordCount"], 1)
        self.assertEqual(result["data"]["tables"][0]["rows"][0]["pilotId"], "sample-1")

    def test_caac_detail_resolves_name_through_list_then_renders_all_sections(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(CAAC_LIST, url="https://fsop.example.test/list", content_type="application/json"),
            FakeResponse(CAAC_NAME_LIST, url="https://fsop.example.test/list", content_type="application/json"),
            FakeResponse(CAAC_DETAIL, url="https://fsop.example.test/detail", content_type="application/json"),
        ])
        executor.load_credentials("yzzzm=a; JSESSIONID=session-value; home=home-value", "caac-fsop")
        result = executor.execute("caac-pilot-export.pilot-detail", {
            "pilotname": "样例人员",
            "archiveNo": "00000001",
        })

        self.assertEqual(session.requests[-2]["data"]["pilotname"], "样例人员")
        self.assertEqual(session.requests[-1]["data"], {"pilotId": "sample-1"})
        self.assertEqual(result["data"]["summary"]["matchedListRows"], 1)
        self.assertEqual(result["data"]["summary"]["nestedFieldCount"], 2)
        self.assertEqual([table["title"] for table in result["data"]["tables"]], [
            "飞行员详情", "layerInfosList", "educationList",
        ])
        self.assertNotIn("[object Object]", json.dumps(result["data"], ensure_ascii=False))

    def test_flight_query_returns_table_json_and_raw_body(self) -> None:
        executor, session = self.create_executor([FakeResponse(QUERY_PAGE_HTML), FakeResponse(IEB_HOME_HTML), FakeResponse(FLIGHT_RESULT_HTML)])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        result = executor.execute("flight-stats.query", {
            "staffNum": "900001",
            "startStr": "2026-01-01",
            "endStr": "2026-08-20",
        })
        table = result["data"]["tables"][0]
        self.assertEqual(table["columns"], ["员工号", "姓名", "飞行时间", "起落总数"])
        self.assertEqual(table["rows"][0]["飞行时间"], "12:30")
        self.assertEqual(result["data"]["summary"]["recordCount"], 1)
        self.assertEqual(result["body"], FLIGHT_RESULT_HTML)
        self.assertNotIn("Set-Cookie", result["headers"])
        self.assertEqual(session.requests[-1]["method"], "GET")

    def test_lock_submit_uses_lazy_metadata_and_employee_validation(self) -> None:
        identity = json.dumps({
            "permissionFlag": "true",
            "nameInfo": "测试人员",
            "deptInfo": "测试部门",
        }, ensure_ascii=False)
        executor, session = self.create_executor([
            FakeResponse(QUERY_PAGE_HTML),
            FakeResponse(IEB_HOME_HTML),
            FakeResponse(ENTRY_HTML),
            FakeResponse(identity, content_type="application/json"),
            FakeResponse(LOCK_RESULT_HTML),
        ])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        result = executor.execute("lock-entry.submit", {
            "staffnum": "900001",
            "lockType": "BS_STUDY",
            "lockTimeType": "1",
            "startDt": "2026-10-08T08:59",
            "endDt": "2026-10-08T19:59",
            "lockRemark": "测试备注",
        })
        self.assertEqual([table["id"] for table in result["data"]["tables"]], ["results", "conflicts"])
        self.assertEqual(result["data"]["tables"][0]["rows"][0]["锁班状态"], "待审批")
        self.assertEqual(
            result["data"]["summary"],
            {"resultCount": 1, "conflictCount": 0, "outcome": "已返回锁班结果"},
        )
        submit_data = session.requests[-1]["data"]
        self.assertIn(("lockTypeDesc", "业务学习"), submit_data)
        self.assertIn(("chnName", "测试人员"), submit_data)
        self.assertIn(("orgUnitName", "测试部门"), submit_data)
        self.assertIn(("lockDays", "1"), submit_data)
        self.assertEqual(
            session.requests[-2]["url"],
            self.catalog.get_execution_request("lock-entry.submit", "validate-employee").url,
        )

    def test_lock_submit_renders_result_table_fragment_without_wrapper(self) -> None:
        identity = json.dumps({
            "permissionFlag": "true",
            "nameInfo": "测试人员",
            "deptInfo": "测试部门",
        }, ensure_ascii=False)
        executor, _session = self.create_executor([
            FakeResponse(QUERY_PAGE_HTML),
            FakeResponse(IEB_HOME_HTML),
            FakeResponse(ENTRY_HTML),
            FakeResponse(identity, content_type="application/json"),
            FakeResponse(LOCK_RESULT_TABLE_ONLY_HTML),
        ])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        result = executor.execute("lock-entry.submit", {
            "staffnum": "900001",
            "lockType": "BS_STUDY",
            "lockTimeType": "1",
            "startDt": "2026-10-08T08:59",
            "endDt": "2026-10-08T19:59",
            "lockRemark": "测试备注",
        })
        self.assertEqual(result["data"]["summary"]["resultCount"], 1)
        self.assertEqual(result["data"]["tables"][0]["rows"][0]["锁班状态"], "待审批")

    def test_personnel_info_executes_multipart_json_and_html_table_requests(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(QUERY_PAGE_HTML),
            FakeResponse(IEB_HOME_HTML),
            FakeResponse(BASIC_INFO_JSON, content_type="application/json"),
            FakeResponse(TECHNICAL_RESULT_HTML),
        ])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")

        basic = executor.execute("personnel-info.basic", {"staffNum": "900001"})
        self.assertEqual([table["id"] for table in basic["data"]["tables"]], [
            "empDto", "eduList", "workList", "titleList", "relationList",
        ])
        self.assertEqual(session.requests[-1]["files"], {"staffNum": (None, "900001")})
        self.assertIsNone(session.requests[-1]["data"])

        technical = executor.execute("personnel-info.technical", {"staffNum": "900001"})
        self.assertEqual(technical["data"]["summary"]["recordCount"], 1)
        self.assertEqual(technical["data"]["tables"][0]["rows"][0]["技术等级"], "机长")
        self.assertEqual(session.requests[-1]["data"]["staffNum"], "900001")

    def test_qualification_query_uses_fixed_code_and_parses_page_info(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(QUERY_PAGE_HTML),
            FakeResponse(IEB_HOME_HTML),
            FakeResponse(QUALIFICATION_PAGE_INFO, content_type="application/json"),
        ])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        result = executor.execute("qualification-monitor.operating-90d3f", {
            "qualType": "ATTEMPTED_OVERRIDE",
            "pageNum": 2,
            "pageSize": 20,
        })

        self.assertEqual(result["data"]["summary"], {
            "recordCount": 2,
            "total": 42,
            "pages": 3,
            "pageNum": 2,
            "pageSize": 20,
            "hasNextPage": True,
        })
        table = result["data"]["tables"][0]
        self.assertIn("specialField", table["columns"])
        params = session.requests[-1]["params"]
        self.assertIn(("qualType", "90D3F"), params)
        self.assertNotIn(("qualType", "ATTEMPTED_OVERRIDE"), params)
        self.assertIn(("staffNum", ""), params)
        self.assertIn(("pageNum", "2"), params)
        self.assertEqual(session.requests[-1]["method"], "GET")

    def test_qualification_roster_executes_request_shapes_and_parses_export_rows(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(QUERY_PAGE_HTML),
            FakeResponse(IEB_HOME_HTML),
            FakeResponse(ROSTER_FILTER_HTML),
            FakeResponse("<div>运行资格选择器</div>"),
            FakeResponse(ROSTER_QUALIFICATION_HTML),
            FakeResponse("<div>共 2 条记录</div>"),
            FakeResponse("", content_type="multipart/form-data;charset=utf-8", content=make_roster_export()),
        ])
        executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")

        filters = executor.execute("qualification-roster.filter-page", {})
        self.assertEqual(filters["data"]["tables"][0]["columns"], ["字段", "字段名称", "是否多选", "选项值", "选项名称"])
        self.assertEqual(filters["data"]["summary"], {"fieldCount": 10, "optionCount": 11})

        qualifications = executor.execute("qualification-roster.operating-qualifications", {})
        self.assertEqual(qualifications["data"]["tables"][0]["rows"][0]["资格代码"], "RAMA")
        self.assertEqual(session.requests[-2]["method"], "POST")

        supplied = {
            "fleetCdToArray": ["777", "787"],
            "activeStatusArray": ["ZAIZHI", "WAIBU", "TUIXIU", "LIZHI"],
            "operQualArray": "RAMA",
        }
        query = executor.execute("qualification-roster.query", supplied)
        self.assertEqual(query["data"]["summary"]["total"], 2)
        self.assertEqual(
            [value for name, value in session.requests[-1]["params"] if name == "fleetCdToArray"],
            ["777", "787"],
        )

        exported = executor.execute("qualification-roster.native-export", supplied)
        self.assertEqual(exported["data"]["summary"], {
            "ooxml": True,
            "recordCount": 2,
            "columnCount": 3,
        })
        self.assertEqual(exported["data"]["tables"][0]["columns"], ["员工号", "姓名", "运行资格"])
        self.assertEqual(exported["data"]["tables"][0]["rows"][0]["员工号"], "900001")
        self.assertEqual(exported["data"]["tables"][0]["rows"][1]["员工号"], "090002")
        self.assertEqual(exported["body"], "")

    def test_verified_cookie_is_kept_alive_with_read_only_query_page(self) -> None:
        request_event = threading.Event()
        executor, session = self.create_executor(
            [FakeResponse(QUERY_PAGE_HTML), FakeResponse(IEB_HOME_HTML), FakeResponse(QUERY_PAGE_HTML)],
            keepalive_interval=1,
            request_event=request_event,
        )
        result = executor.load_credentials("JSESSIONID=session-value; iebJSid=browser-value")
        self.assertTrue(result["keepAlive"]["running"])
        request_event.clear()
        self.assertTrue(request_event.wait(timeout=2.5))
        self.assertEqual(session.requests[2]["method"], "GET")
        self.assertIn("showFlytimeManyQuery", str(session.requests[2]["url"]))
        self.assertIsNone(session.requests[2]["data"])

    def test_soc_session_reports_server_rendered_name_without_inventing_staff_number(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(SOC_ENTRY_HTML),
            FakeResponse(SOC_NAVIGATION_HTML, url="https://soc.example.test/opws-web/pages/public/soc.jsp?f=2&s=11&t=1"),
        ])
        loaded = executor.load_credentials("JSESSIONID=soc-session", "soc")
        self.assertTrue(loaded["ready"])
        self.assertEqual(loaded["identity"], {"name": "测试用户"})
        self.assertEqual(
            [request["url"] for request in session.requests],
            [
                self.catalog.get_session_request("soc", "validation").url,
                self.catalog.get_session_request("soc", "identity").url,
            ],
        )

    def test_soc_endpoints_use_shared_core_and_return_structured_tables(self) -> None:
        station_payload = json.dumps({"result": ["郑州"]}, ensure_ascii=False)
        reason_payload = json.dumps({"rows": [{"value": "6", "label": "学习培训"}]}, ensure_ascii=False)
        flight_payload = json.dumps({
            "total": 1,
            "rows": [{
                "fltNr": "1234", "seqNr": "01", "fltDt": "2026-01-15",
                "fltRoute": "CAN-CGO", "fltTime": "08:00-10:00",
                "crewDepDt": "2026-01-15 07:00", "subfleetType": "32A", "alnCd": "CZ",
            }],
        }, ensure_ascii=False)
        validation_payload = json.dumps({
            "total": 1, "failFeedback": "",
            "rows": [{"staffNum": "900001", "chnName": "测试员工"}],
        }, ensure_ascii=False)
        submit_payload = json.dumps({"message": "录入成功！"}, ensure_ascii=False)
        executor, session = self.create_executor([
            FakeResponse(SOC_ENTRY_HTML),
            FakeResponse(SOC_NAVIGATION_HTML),
            FakeResponse(station_payload, content_type="application/json"),
            FakeResponse(reason_payload, content_type="application/json"),
            FakeResponse(flight_payload, content_type="application/json"),
            FakeResponse(validation_payload, content_type="application/json"),
            FakeResponse(submit_payload, content_type="application/json"),
        ])
        executor.load_credentials("JSESSIONID=soc-session", "soc")

        suggestions = executor.execute("soc-positioning.station-suggest", {"dataJson": "zhengzhou"})
        self.assertEqual(suggestions["data"]["tables"][0]["rows"], [{"站点": "郑州"}])
        reasons = executor.execute("soc-positioning.apply-reasons", {})
        self.assertEqual(reasons["data"]["tables"][0]["rows"][0]["label"], "学习培训")
        flights = executor.execute("soc-positioning.flights", {
            "kkTvlApplyVO.fltDt": "2026-01-15",
            "kkTvlApplyVO.depArpCd": "广州",
            "kkTvlApplyVO.arvArpCd": "郑州",
        })
        self.assertEqual(flights["data"]["tables"][0]["rows"][0]["航线"], "CAN-CGO")
        validation = executor.execute("soc-positioning.staff-validation", {
            "staffNums": "900001", "depArpCd": "广州", "arvArpCd": "郑州",
            "fltDt": "2026-01-15", "fltDt2": "2026-01-15", "applyReasonCd": "6",
            "fltRoute": "CAN-CGO",
        })
        self.assertEqual(validation["data"]["tables"][0]["rows"][0]["chnName"], "测试员工")
        submitted = executor.execute("soc-positioning.submit", {
            "kkTvlStaffNum1": "900001", "kkTvlApplyVO.staffNum": "900001",
            "kkTvlApplyVO.fltDt": "2026-01-15", "kkTvlApplyVO.depArpCd": "广州",
            "kkTvlApplyVO.arvArpCd": "郑州", "kkTvlApplyVO.fltNr": "composite",
            "kkTvlApplyVO.fltDt2": "2026-01-15", "kkTvlApplyVO.applyReasonCd": "6",
        })
        self.assertTrue(submitted["data"]["summary"]["success"])
        self.assertEqual(session.requests[-1]["url"], self.catalog.get_endpoint("soc-positioning.submit").url)

    def test_oa_count_workflow_scans_all_pages_and_returns_summary(self) -> None:
        executor, _session = self.create_executor([
            FakeResponse(OA_USER_INFO, url="https://work.example.test/user", content_type="application/json"),
            FakeResponse(OA_WAITING, url="https://work.example.test/waiting", content_type="application/json"),
        ])
        credentials = (
            "curl 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'User-Agent: Example Browser' "
            "-H 'Cookie: SESSION=oa-session; ROUTE-SESSION=oa-route' "
            "--data-raw '{\"moduleMainCategoryId\":-5,\"offsetPageIndex\":0}'"
        )

        executor.load_credentials(credentials, "oa")
        result = executor.execute("oa-read.count", {})

        self.assertEqual(result["data"]["summary"], {
            "total": 3,
            "eligible": 2,
            "skipped": 1,
        })
        self.assertEqual(result["data"]["tables"][0]["rows"], [
            {"模块": "DOC/official-document", "数量": 2, "处理方式": "可执行已阅"},
            {"模块": "OTHER/workflow", "数量": 1, "处理方式": "跳过"},
        ])

    def test_oa_read_workflow_reports_each_result_progressively_and_serially(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(OA_USER_INFO, url="https://work.example.test/user", content_type="application/json"),
            FakeResponse(OA_WAITING, url="https://work.example.test/waiting", content_type="application/json"),
            FakeResponse(OA_SUCCESS, url="https://work.example.test/read-1", content_type="application/json"),
            FakeResponse(OA_SUCCESS, url="https://work.example.test/read-2", content_type="application/json"),
        ])
        credentials = (
            "curl 'https://work.csair.com/oai/work/box/query/waiting' "
            "-H 'User-Agent: Example Browser' "
            "-H 'Cookie: SESSION=oa-session; ROUTE-SESSION=oa-route' "
            "--data-raw '{\"moduleMainCategoryId\":-5,\"offsetPageIndex\":0}'"
        )

        loaded = executor.load_credentials(credentials, "oa")
        progress: list[dict[str, object]] = []
        result = executor.execute("oa-read.read", {"count": 5000}, progress.append)

        self.assertTrue(loaded["ready"])
        self.assertEqual(loaded["identity"], {"staffNumber": "900001", "name": "示例用户"})
        self.assertEqual(session.headers["User-Agent"], "Example Browser")
        self.assertEqual(result["data"]["summary"], {
            "scanned": 3,
            "eligible": 2,
            "skipped": 1,
            "requested": 5000,
            "target": 2,
            "success": 2,
            "failed": 0,
        })
        self.assertEqual([
            len(snapshot["data"]["tables"][0]["rows"])  # type: ignore[index]
            for snapshot in progress
        ], [0, 1, 2])
        self.assertEqual(
            [request["url"] for request in session.requests],
            [
                self.catalog.get_session_request("oa", "validation").url,
                self.catalog.get_execution_request("oa-read.read", "scan-waiting").url,
                self.catalog.get_execution_request("oa-read.read", "mark-read").url,
                self.catalog.get_execution_request("oa-read.read", "mark-read").url,
            ],
        )
        self.assertEqual(session.requests[1]["json"], {
            "offsetPageIndex": 0,
            "pageMode": "page",
            "resultCountPerPage": 100,
        })
        self.assertEqual(session.requests[2]["json"], {
            "approveOpinionType": None,
            "approveOpinionContent": None,
            "docId": "doc-1",
            "docType": "type-1",
            "flowStepId": "step-1",
        })
        self.assertEqual(session.requests[3]["json"]["docId"], "doc-2")
        statuses = executor.all_session_statuses()
        self.assertFalse(statuses["flight-portal"]["ready"])
        self.assertTrue(statuses["oa"]["ready"])

    def test_oa_read_workflow_continues_after_non_session_business_failure(self) -> None:
        executor, session = self.create_executor([
            FakeResponse(OA_USER_INFO, url="https://work.example.test/user", content_type="application/json"),
            FakeResponse(OA_WAITING, url="https://work.example.test/waiting", content_type="application/json"),
            FakeResponse(OA_FAILURE, url="https://work.example.test/read-1", content_type="application/json"),
            FakeResponse(OA_SUCCESS, url="https://work.example.test/read-2", content_type="application/json"),
        ])
        executor.load_credentials("SESSION=oa-session; ROUTE-SESSION=oa-route", "oa")

        result = executor.execute("oa-read.read", {"count": 2})

        self.assertEqual(result["data"]["summary"]["success"], 1)
        self.assertEqual(result["data"]["summary"]["failed"], 1)
        self.assertEqual([request["url"] for request in session.requests[-2:]], [
            self.catalog.get_execution_request("oa-read.read", "mark-read").url,
            self.catalog.get_execution_request("oa-read.read", "mark-read").url,
        ])

    def test_keepalive_interval_stays_within_requested_range(self) -> None:
        values = [random_keepalive_interval() for _ in range(200)]
        self.assertTrue(all(30 <= value <= 60 for value in values))


if __name__ == "__main__":
    unittest.main()
