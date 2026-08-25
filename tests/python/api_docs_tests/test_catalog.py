from __future__ import annotations

import json
import unittest

from .common import CATALOG_ROOT
from api_docs.catalog import ApiCatalog


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ApiCatalog(CATALOG_ROOT)

    def test_catalog_exposes_cross_system_business_apis(self) -> None:
        modules = self.catalog.as_dict()["modules"]
        self.assertTrue({
            "飞行经历查询接口",
            "飞行人员锁班接口",
            "飞行人员信息查询接口",
            "OA 公文已阅接口",
            "资质监控按资质查询接口",
        }.issubset({module["name"] for module in modules}))
        self.assertTrue({
            "flight-stats.query",
            "lock-entry.submit",
            "personnel-info.basic",
            "oa-read.count",
        }.issubset(self.catalog.endpoints))
        personnel = modules[2]
        self.assertEqual(
            [group["name"] for group in personnel["groups"]],
            ["基础信息", "技术等级", "运行资格", "训练检查记录"],
        )
        systems = self.catalog.as_dict()["systems"]
        self.assertEqual([system["id"] for system in systems], ["flight-portal", "oa", "soc", "caac-fsop"])
        self.assertEqual(systems[0]["navigationUrl"], "https://ieb.csair.com/index/index")
        self.assertEqual(systems[1]["credentialRequestUrl"], "https://work.csair.com/oai/work/box/query/waiting")
        self.assertEqual(self.catalog.as_dict()["schemaVersion"], 2)

    def test_qualification_monitor_exposes_29_fixed_query_contracts(self) -> None:
        records = [
            record
            for full_id, record in self.catalog.endpoints.items()
            if full_id.startswith("qualification-monitor.")
        ]
        self.assertEqual(len(records), 29)
        self.assertEqual(
            {record.endpoint["groupId"] for record in records},
            {"operating", "qualification", "special"},
        )
        codes = []
        for record in records:
            self.assertEqual(record.endpoint["method"], "GET")
            self.assertEqual(record.endpoint["path"], "/newieb/qualification/alarm/new/queryAlarmDetail")
            parameters = {item["name"]: item for item in record.endpoint["parameters"]}
            self.assertTrue(parameters["qualType"]["fixed"])
            self.assertTrue(parameters["staffNum"]["includeWhenEmpty"])
            self.assertEqual(parameters["pageSize"]["default"], "20")
            codes.append(parameters["qualType"]["default"])
        self.assertEqual(len(set(codes)), 29)

    def test_request_roles_separate_sessions_execution_and_related_requests(self) -> None:
        serialized = json.dumps(self.catalog.as_dict(), ensure_ascii=False)
        self.assertEqual(len(self.catalog.request_definitions), 22)

        ieb_validation = self.catalog.get_session_request("flight-portal", "validation")
        ieb_keepalive = self.catalog.get_session_request("flight-portal", "keepAlive")
        oa_validation = self.catalog.get_session_request("oa", "validation")
        oa_keepalive = self.catalog.get_session_request("oa", "keepAlive")
        self.assertEqual(ieb_validation.full_id, "flight-stats.query-page")
        self.assertEqual(ieb_keepalive.full_id, ieb_validation.full_id)
        self.assertEqual(oa_validation.full_id, "oa-read.user-info")
        self.assertEqual(oa_keepalive.full_id, oa_validation.full_id)

        direct = [
            record
            for record in self.catalog.endpoints.values()
            if record.endpoint["execution"]["kind"] == "direct-http"
        ]
        self.assertEqual(len(direct), 43)
        for record in direct:
            primary = [
                step
                for step in self.catalog.get_execution_steps(record.full_id)
                if step["requestRef"] == "$endpoint"
            ]
            self.assertEqual(len(primary), 1)
            self.assertEqual(primary[0]["role"], "primary")
            self.assertEqual(primary[0]["cardinality"], "once")

        self.assertEqual(
            [step["id"] for step in self.catalog.get_execution_steps("lock-entry.submit")],
            ["load-lock-types", "validate-employee", "submit"],
        )
        self.assertEqual(
            self.catalog.get_execution_request("lock-entry.submit", "validate-employee").full_id,
            "lock-entry.employee-validation",
        )
        self.assertEqual(
            self.catalog.get_option_source("lock-types").full_id,
            "lock-entry.entry-page",
        )
        lock_related = self.catalog.get_related_requests("lock-entry")
        self.assertEqual(
            {item["kind"] for item in lock_related},
            {"option-source", "reference-query", "state-action"},
        )
        state_actions = {
            item["requestRef"]
            for item in lock_related
            if item["kind"] == "state-action"
        }
        self.assertEqual(state_actions, {
            "lock-entry.approve",
            "lock-entry.withdraw",
            "lock-entry.unlock",
            "lock-entry.reject",
        })
        qualification_related = self.catalog.get_related_requests("qualification-monitor")
        self.assertEqual(
            {item["kind"] for item in qualification_related},
            {"metadata", "option-source", "export"},
        )
        self.assertEqual(self.catalog.get_related_requests("personnel-info"), [])
        self.assertEqual(self.catalog.get_session_request("soc", "validation").full_id, "soc-positioning.entry-page")
        self.assertEqual(self.catalog.get_session_request("soc", "identity").full_id, "soc-positioning.navigation-page")
        self.assertEqual(self.catalog.get_session_request("caac-fsop", "validation").full_id, "caac-pilot-export.pilot-list-session")
        self.assertEqual(self.catalog.get_session_request("caac-fsop", "keepAlive").full_id, "caac-pilot-export.pilot-list-session")
        self.assertEqual(self.catalog.get_endpoint("soc-positioning.submit").endpoint["risk"], "write")

    def test_personnel_info_keeps_verified_request_contracts(self) -> None:
        basic = self.catalog.get_endpoint("personnel-info.basic").endpoint
        training = self.catalog.get_endpoint("personnel-info.training-records").endpoint
        experience = self.catalog.get_endpoint("personnel-info.training-experiences").endpoint

        self.assertEqual(basic["path"], "/newieb/hrInfo/showEmpInfo")
        self.assertEqual(basic["requestEncoding"], "multipart/form-data")
        self.assertEqual([item["name"] for item in basic["response"]["fields"]], [
            "empDto", "eduList", "workList", "titleList", "relationList",
        ])
        self.assertEqual(training["path"], "/newieb/basics/trainingRecordList")
        self.assertEqual({item["name"] for item in training["parameters"]}, {
            "page", "staffId", "fuzzyQuery", "newMachineId", "trainName",
        })
        self.assertEqual(experience["path"], "/newieb/basics/trainResultList")

    def test_oa_catalog_keeps_count_and_progressive_read_workflows(self) -> None:
        count_endpoint = self.catalog.get_endpoint("oa-read.count")
        read = self.catalog.get_endpoint("oa-read.read")

        self.assertEqual(count_endpoint.endpoint["execution"]["kind"], "local-workflow")
        self.assertEqual(count_endpoint.endpoint["parameters"], [])
        self.assertEqual(read.endpoint["execution"]["kind"], "local-workflow")
        self.assertTrue(read.endpoint["progressive"])
        count = read.endpoint["parameters"][0]
        self.assertEqual(count["name"], "count")
        self.assertEqual(count["minimum"], 1)
        self.assertEqual(
            [step["id"] for step in self.catalog.get_execution_steps("oa-read.count")],
            ["scan-waiting"],
        )
        self.assertEqual(
            [step["id"] for step in self.catalog.get_execution_steps("oa-read.read")],
            ["scan-waiting", "mark-read"],
        )
        have_read = self.catalog.get_execution_request("oa-read.read", "mark-read")
        self.assertEqual(have_read.url, "https://work.csair.com/oai/doc/pc/form/sw/haveRead")
        self.assertEqual(
            set(have_read.endpoint["parameters"]),
            {"approveOpinionType=null", "approveOpinionContent=null", "docId", "docType", "flowStepId"},
        )

    def test_friendly_controls_keep_derived_portal_fields_documented(self) -> None:
        endpoint = self.catalog.get_endpoint("lock-entry.submit").endpoint
        controls = {parameter["name"]: parameter for parameter in endpoint["parameters"]}
        self.assertEqual(controls["lockType"]["optionSource"], "lock-types")
        self.assertEqual(controls["startDt"]["type"], "datetime-local")
        self.assertEqual(controls["lockYearAndMonth"]["type"], "month")
        self.assertEqual(controls["lockStartHourAndMinute"]["type"], "time")
        self.assertTrue(controls["lockDaysNum"]["repeatable"])
        for derived in ("dateSplitFlag", "lockDays", "lockTypeDesc", "chnName", "orgUnitName", "random"):
            self.assertIn(derived, controls)
            self.assertTrue(controls[derived]["fixed"])

if __name__ == "__main__":
    unittest.main()
