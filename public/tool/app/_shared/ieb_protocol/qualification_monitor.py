from __future__ import annotations

from typing import Mapping

from .base import IebContractError, IebSession
from .qualification_monitor_contract import (
    build_filter_params,
    build_query_params,
    parse_classification_tree,
    parse_page_info,
    validate_ooxml,
)
from .qualification_monitor_models import QualificationGroup, QualificationPage


CLASSIFICATION_PATH = "/newieb/qualification/alarm/new/queryQualificationTypeParent"
QUERY_PATH = "/newieb/qualification/alarm/new/queryAlarmDetail"
EXPORT_PATH = "/newieb/qualification/alarm/new/exportQualificationInfoExcel"


class QualificationMonitorProtocol:
    """资质分类、PageInfo 查询和门户原生导出的生产调用。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session

    def request_classification(self) -> tuple[object, list[QualificationGroup]]:
        response = self.session.request(
            "GET",
            CLASSIFICATION_PATH,
            headers={"Accept": "application/json, text/plain, */*"},
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise IebContractError("资质分类接口未返回有效 JSON") from error
        return response, parse_classification_tree(payload)

    def load_metadata(self) -> tuple[list[QualificationGroup], dict[str, str]]:
        _response, groups = self.request_classification()
        _identity_response, identity = self.session.fetch_identity()
        return groups, identity

    def check_session(self) -> None:
        self.request_classification()

    def request_page(
        self,
        qualification_code: str,
        filters: Mapping[str, object] | None = None,
        page_number: object = 1,
        page_size: object = 20,
    ) -> tuple[object, QualificationPage]:
        response = self.session.request(
            "GET",
            QUERY_PATH,
            params=build_query_params(qualification_code, filters, page_number, page_size),
            headers={"Accept": "application/json, text/plain, */*"},
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise IebContractError("资质查询接口未返回有效 JSON") from error
        return response, parse_page_info(payload)

    def request_export(
        self,
        qualification_code: str,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[object, bytes]:
        response = self.session.request(
            "GET",
            EXPORT_PATH,
            params=build_filter_params(qualification_code, filters),
            headers={"Accept": "*/*"},
        )
        content = bytes(response.content or b"")
        validate_ooxml(content)
        return response, content
