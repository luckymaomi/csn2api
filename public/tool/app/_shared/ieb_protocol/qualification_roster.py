from __future__ import annotations

import time

from .base import IebSession
from .roster_contract import (
    build_filter_params,
    parse_filter_fields,
    parse_operating_qualifications,
    parse_query_result,
    validate_ooxml,
)
from .roster_models import FilterField, OperatingQualification, QueryFilters


FILTER_PAGE_PATH = "/newieb/basics/showEmpprofileCompositeListPageNew"
QUALIFICATION_DIALOG_PATH = "/newieb/basics/showChooseOperQualificationDialog"
QUALIFICATION_LIST_PATH = "/newieb/basics/showChooseOperQualificationList"
QUERY_PATH = "/newieb/basics/showEmpProfileCompositeResult"
EXPORT_PATH = "/newieb/basics/createEmpProfileCompositeExcel"


class QualificationRosterProtocol:
    """运行资质元数据、单资格查询和普通导出的生产调用。"""

    def __init__(self, session: IebSession) -> None:
        self.session = session
        self.filter_fields: list[FilterField] = []
        self.qualifications: list[OperatingQualification] = []

    def load_metadata(self) -> tuple[list[FilterField], list[OperatingQualification], dict[str, str]]:
        _page, fields = self.request_filter_fields()
        _listing, qualifications = self.request_qualifications()
        _response, identity = self.session.fetch_identity()
        self.filter_fields = fields
        self.qualifications = qualifications
        return fields, qualifications, identity

    def request_filter_fields(self) -> tuple[object, list[FilterField]]:
        page = self.session.request(
            "GET", FILTER_PAGE_PATH,
            params={"random": f"{time.time():.6f}"},
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        fields = parse_filter_fields(str(page.text or ""))
        return page, fields

    def request_qualifications(self) -> tuple[object, list[OperatingQualification]]:
        self.session.request(
            "POST", QUALIFICATION_DIALOG_PATH,
            data={}, headers={"Accept": "text/html, */*; q=0.01"},
        )
        listing = self.session.request(
            "GET", QUALIFICATION_LIST_PATH,
            params={"qualCd": "", "chnDesc": ""},
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        qualifications = parse_operating_qualifications(str(listing.text or ""))
        return listing, qualifications

    def check_session(self) -> None:
        response = self.session.request(
            "GET", FILTER_PAGE_PATH,
            params={"random": f"{time.time():.6f}"},
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        parse_filter_fields(str(response.text or ""))

    def request_query(self, filters: QueryFilters, qualification_code: str) -> tuple[object, int, list[str], list[dict[str, str]]]:
        response = self.session.request(
            "GET", QUERY_PATH,
            params=build_filter_params(filters, qualification_code, page=1),
            headers={"Accept": "text/html, */*; q=0.01"},
        )
        total, headers, rows = parse_query_result(str(response.text or ""))
        return response, total, headers, rows

    def request_export(self, filters: QueryFilters, qualification_code: str) -> tuple[object, bytes]:
        response = self.session.request(
            "GET", EXPORT_PATH,
            params=build_filter_params(filters, qualification_code),
            headers={"Accept": "*/*"},
        )
        content = bytes(response.content or b"")
        validate_ooxml(content)
        return response, content
