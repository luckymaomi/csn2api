from __future__ import annotations

import time

from bs4 import BeautifulSoup

from .base import IebContractError, IebSession
from .personnel_contract import (
    OPERATION_HEADERS,
    TECHNICAL_HEADERS,
    TRAINING_EXPERIENCE_HEADERS,
    build_employee_query_params,
    parse_basic_payload,
    parse_detail_table,
    parse_employee_identity,
    parse_training_record_pages,
)


VERIFY_PATH = "/newieb/basics/showEmpprofileCompositeListPageNew"
EMPLOYEE_PATH = "/newieb/basics/showEmpProfileCompositeResult"
BASIC_INFO_PATH = "/newieb/hrInfo/showEmpInfo"
TECHNICAL_PATH = "/newieb/basics/qualList"
OPERATION_PATH = "/newieb/basics/showSingleEmpHisOperQualListByempId"
TRAINING_RECORD_PATH = "/newieb/basics/trainingRecordList"
TRAINING_EXPERIENCE_PATH = "/newieb/basics/trainResultList"


class PersonnelProtocol:
    """飞行人员身份、基础资料、资质和训练记录的只读调用。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session

    def _verify_page(self, response: object) -> None:
        soup = BeautifulSoup(str(response.text or ""), "html.parser")  # type: ignore[attr-defined]
        if soup.select_one("#showEmpProfileCompositeListPageForm") is None:
            raise IebContractError("凭据未进入技术资料查询页")

    def validate_session(self) -> tuple[object, dict[str, str]]:
        response = self.session.request("GET", VERIFY_PATH, params={"random": str(time.time_ns())})
        self._verify_page(response)
        _identity_response, identity = self.session.fetch_identity()
        return response, identity

    def check_session(self) -> None:
        response = self.session.request("GET", VERIFY_PATH, params={"random": str(time.time_ns())})
        self._verify_page(response)

    def request_employee(self, employee_id: str, expected_name: str = "") -> tuple[object, dict[str, str]]:
        response = self.session.request("GET", EMPLOYEE_PATH, params=build_employee_query_params(employee_id))
        identity = parse_employee_identity(str(response.text or ""), employee_id, expected_name)
        return response, identity

    def request_basic(self, employee_id: str) -> tuple[object, dict[str, object]]:
        response = self.session.request(
            "POST", BASIC_INFO_PATH,
            data=None,
            files={"staffNum": (None, employee_id)},
        )
        try:
            payload = response.json()
        except Exception as error:
            raise IebContractError("门户基础信息未返回有效 JSON") from error
        return response, parse_basic_payload(payload)

    def request_technical(self, employee_id: str) -> tuple[object, list[dict[str, str]]]:
        response = self.session.request("POST", TECHNICAL_PATH, data={"staffNum": employee_id, "currentStr": str(int(time.time() * 1000))})
        return response, parse_detail_table(str(response.text or ""), "#qualList", TECHNICAL_HEADERS)

    def request_operation(self, employee_id: str) -> tuple[object, list[dict[str, str]]]:
        response = self.session.request("POST", OPERATION_PATH, data={"empid": employee_id, "date": str(int(time.time() * 1000))})
        return response, parse_detail_table(str(response.text or ""), "#showSingleEmpOperQualList", OPERATION_HEADERS)

    def request_training_record_page(self, employee_id: str, page: int) -> object:
        return self.session.request("POST", TRAINING_RECORD_PATH, data={
            "page": str(page), "staffId": employee_id, "fuzzyQuery": "true",
            "newMachineId": "", "trainName": "",
        })

    def request_training_records(self, employee_id: str) -> list[dict[str, str]]:
        return parse_training_record_pages(
            lambda page: str(self.request_training_record_page(employee_id, page).text or ""),
        )

    def request_training_experiences(self, employee_id: str) -> tuple[object, list[dict[str, str]]]:
        response = self.session.request("POST", TRAINING_EXPERIENCE_PATH, data={"staffNum": employee_id, "trainName": ""})
        rows = parse_detail_table(
            str(response.text or ""),
            "#trainResultList, #empProfile_trainResultList",
            TRAINING_EXPERIENCE_HEADERS,
        )
        return response, [{**row, "来源页码": "1"} for row in rows]

    def request_all(self, employee_id: str, expected_name: str = "") -> dict[str, object]:
        _employee_response, identity = self.request_employee(employee_id, expected_name)
        _basic_response, basic = self.request_basic(employee_id)
        _technical_response, technical = self.request_technical(employee_id)
        _operation_response, operation = self.request_operation(employee_id)
        training_records = self.request_training_records(employee_id)
        _experience_response, training_experiences = self.request_training_experiences(employee_id)
        return {
            "pageName": identity["name"],
            "basic": basic,
            "technical": technical,
            "operation": operation,
            "trainingRecords": training_records,
            "trainingExperiences": training_experiences,
        }
