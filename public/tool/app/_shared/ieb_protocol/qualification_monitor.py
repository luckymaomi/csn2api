from __future__ import annotations

from typing import Mapping

from .base import IebContractError, IebSession
from .qualification_monitor_contract import (
    build_filter_params,
    build_inspector_filter_params,
    build_inspector_query_params,
    build_query_params,
    parse_classification_tree,
    parse_page_info,
    validate_ooxml,
)
from .qualification_monitor_models import QualificationGroup, QualificationPage


CLASSIFICATION_PATH = "/newieb/qualification/alarm/new/queryQualificationTypeParent"
ALARM_QUERY_PATH = "/newieb/qualification/alarm/new/queryAlarmDetail"
ALARM_EXPORT_PATH = "/newieb/qualification/alarm/new/exportQualificationInfoExcel"
INSPECTOR_QUERY_PATH = "/newieb/zhftcCheckerInfo/pageZhftcCheckerInfo"
INSPECTOR_OPTIONS_PATH = "/newieb/zhftcCheckerInfo/getFleetCdAndBase"
INSPECTOR_EXPORT_PATH = "/newieb/zhftcCheckerInfo/exportZhftcCheckerInfoExcel"
INSPECTOR_CODE = "JCY"


class QualificationMonitorProtocol:
    """资质分类、分页查询和门户导出的生产调用。"""

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

    def validate_session(self) -> tuple[object, dict[str, str]]:
        return self.session.fetch_identity()

    def load_metadata(self) -> list[QualificationGroup]:
        _response, groups = self.request_classification()
        return groups

    def check_session(self) -> None:
        self.validate_session()

    def request_page(
        self,
        qualification_code: str,
        filters: Mapping[str, object] | None = None,
        page_number: object = 1,
        page_size: object = 20,
    ) -> tuple[object, QualificationPage]:
        inspector = str(qualification_code or "").strip() == INSPECTOR_CODE
        response = self.session.request(
            "GET",
            INSPECTOR_QUERY_PATH if inspector else ALARM_QUERY_PATH,
            params=(
                build_inspector_query_params(filters, page_number, page_size)
                if inspector
                else build_query_params(qualification_code, filters, page_number, page_size)
            ),
            headers={"Accept": "application/json, text/plain, */*"},
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise IebContractError("资质查询接口未返回有效 JSON") from error
        return response, parse_page_info(payload)

    def request_all_pages(
        self,
        qualification_code: str,
        filters: Mapping[str, object] | None = None,
        page_size: object = 20,
    ) -> list[QualificationPage]:
        """按 PageInfo 契约严格收敛当前资质的全部分页。"""
        _response, first = self.request_page(qualification_code, filters, 1, page_size)
        pages = [first]
        if first.total == 0:
            return pages
        if first.pages < 1:
            raise IebContractError("资质查询首分页与总页数契约不一致")
        if first.pages == 1:
            if first.has_next_page or len(first.rows) != first.total:
                raise IebContractError("资质查询单页与总数契约不一致")
            return pages
        if not first.has_next_page:
            raise IebContractError("资质查询首分页结束标记契约不一致")
        for page_number in range(2, first.pages + 1):
            _response, page = self.request_page(qualification_code, filters, page_number, first.page_size)
            if page.page_number != page_number or page.page_size != first.page_size:
                raise IebContractError("资质查询分页响应页码契约不一致")
            expected_next = page_number < first.pages
            if page.has_next_page != expected_next:
                raise IebContractError("资质查询分页结束标记契约不一致")
            pages.append(page)
        if sum(len(page.rows) for page in pages) != first.total:
            raise IebContractError("资质查询分页行数与总数不一致")
        return pages

    def request_export(
        self,
        qualification_code: str,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[object, bytes]:
        inspector = str(qualification_code or "").strip() == INSPECTOR_CODE
        response = self.session.request(
            "GET",
            INSPECTOR_EXPORT_PATH if inspector else ALARM_EXPORT_PATH,
            params=(
                build_inspector_filter_params(filters)
                if inspector
                else build_filter_params(qualification_code, filters)
            ),
            headers={"Accept": "*/*"},
        )
        content = bytes(response.content or b"")
        validate_ooxml(content)
        return response, content
