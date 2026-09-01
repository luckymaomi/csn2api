from __future__ import annotations

import json
import sys
import unittest
from collections import deque
from pathlib import Path

from .common import SHARED_ROOT

API_ROOT = SHARED_ROOT.parent / "api-docs"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from api_docs.catalog import ApiCatalog
from api_docs.executor import ApiExecutor


PAGE = '<form id="showflyTimeExperienceQueryForm" action="/newieb/flytime/showFlytimeManyQueryList"></form>'
HOME = '<div id="personalInfo"><span class="name-txt">示例甲</span></div><div class="detailInfo"><div class="empid"><span title="900001"></span></div></div>'
TIMELINE = '<button onclick="showflyTimeDetail(\'1\',\'900001\',\'示例甲\',\'2026\',\'\',\'32A\')">2026</button>'
DETAIL = '''<table><tr><th>序号</th><th>航班号</th><th>机型</th><th>日期</th><th>左座</th><th>右座</th><th>操纵</th><th>观察</th><th>离场</th><th>到达</th><th>飞行时间</th><th>夜航</th><th>飞行阶段</th><th>人工飞行时间</th><th>人工飞行方式</th></tr><tr><td>1</td><td>CZ1</td><td>32A</td><td>2026-08-01</td><td>1</td><td></td><td>1</td><td></td><td>CAN</td><td>PEK</td><td>01:00</td><td></td><td>巡航</td><td></td></tr><tr><td>自动驾驶</td></tr></table>'''


class Response:
    status_code = 200
    reason = "OK"
    headers = {"Content-Type": "text/html; charset=utf-8"}

    def __init__(self, text: str, url: str = "https://ieb.csair.com/result") -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self.url = url


class Session:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.cookies = type("Cookies", (), {"set": lambda self, *_args, **_kwargs: None, "clear": lambda self: None})()
        self.responses = deque([Response(PAGE), Response(HOME, "https://ieb.csair.com/index/index"), Response(TIMELINE), Response(DETAIL)])
        self.requests: list[dict[str, object]] = []

    def request(self, *args: object, **kwargs: object) -> Response:
        if args:
            kwargs = {"method": args[0], "url": args[1], **kwargs}
        self.requests.append(kwargs)
        return self.responses.popleft()

    def close(self) -> None:
        return None


class ApiExecutorTests(unittest.TestCase):
    def test_month_detail_api_uses_timeline_then_real_month_request(self) -> None:
        session = Session()
        catalog = ApiCatalog(API_ROOT / "catalog")
        executor = ApiExecutor(catalog, session_factory=lambda: session)
        try:
            executor.load_credentials("JSESSIONID=session; iebJSid=browser")
            result = executor.execute("flight-detail.query-month", {"staffNum": "900001", "staffName": "示例甲", "startStr": "2026/8"})
            self.assertEqual(result["data"]["summary"]["recordCount"], 1)
            self.assertEqual(result["data"]["tables"][0]["rows"][0]["人工飞行方式"], "自动驾驶")
            self.assertEqual(session.requests[-2]["method"], "POST")
            self.assertEqual(session.requests[-1]["method"], "GET")
            self.assertEqual(session.requests[-1]["params"]["dateType"], "2")
            self.assertEqual(session.requests[-1]["params"]["startStr"], "2026-08")
        finally:
            executor.close()


if __name__ == "__main__":
    unittest.main()
