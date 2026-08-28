from __future__ import annotations

import io
import json
import re
import zipfile
from xml.etree import ElementTree

from ieb_protocol.qualification_monitor_models import QualificationPage


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
INVALID_XML_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

ElementTree.register_namespace("", MAIN_NS)
ElementTree.register_namespace("r", REL_NS)
ElementTree.register_namespace("pr", PACKAGE_REL_NS)
ElementTree.register_namespace("ct", CONTENT_TYPE_NS)


def _cell_text(value: object) -> str:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    text = "" if value is None else str(value)
    return INVALID_XML_CONTROL.sub("", text)[:32767]


def _column_name(index: int) -> str:
    name = ""
    value = index
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xml_bytes(root: ElementTree.Element) -> bytes:
    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)


def _worksheet(columns: list[str], rows: list[dict[str, object]]) -> bytes:
    root = ElementTree.Element(f"{{{MAIN_NS}}}worksheet")
    sheet_data = ElementTree.SubElement(root, f"{{{MAIN_NS}}}sheetData")
    all_values = [columns, *([ [row.get(column, "") for column in columns] for row in rows ])]
    for row_number, values in enumerate(all_values, start=1):
        row = ElementTree.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_number)})
        for column_number, value in enumerate(values, start=1):
            cell = ElementTree.SubElement(
                row,
                f"{{{MAIN_NS}}}c",
                {"r": f"{_column_name(column_number)}{row_number}", "t": "inlineStr"},
            )
            inline = ElementTree.SubElement(cell, f"{{{MAIN_NS}}}is")
            text = ElementTree.SubElement(inline, f"{{{MAIN_NS}}}t")
            text.text = _cell_text(value)
    return _xml_bytes(root)


def build_inspector_query_workbook(pages: list[QualificationPage]) -> bytes:
    """把 JCY 分页 JSON 按动态字段生成可下载的单 Sheet OOXML。"""
    if not pages:
        raise ValueError("检查员库分页不能为空")
    rows = [row for page in pages for row in page.rows]
    columns: list[str] = []
    for row in rows:
        for name in row:
            text = str(name)
            if text not in columns:
                columns.append(text)
    values = [{column: row.get(column, "") for column in columns} for row in rows]

    content_types = ElementTree.Element(f"{{{CONTENT_TYPE_NS}}}Types")
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPE_NS}}}Default",
        {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"},
    )
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPE_NS}}}Default",
        {"Extension": "xml", "ContentType": "application/xml"},
    )
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPE_NS}}}Override",
        {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"},
    )
    ElementTree.SubElement(
        content_types,
        f"{{{CONTENT_TYPE_NS}}}Override",
        {"PartName": "/xl/worksheets/sheet1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"},
    )

    package_rels = ElementTree.Element(f"{{{PACKAGE_REL_NS}}}Relationships")
    ElementTree.SubElement(
        package_rels,
        f"{{{PACKAGE_REL_NS}}}Relationship",
        {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml"},
    )

    workbook = ElementTree.Element(f"{{{MAIN_NS}}}workbook")
    sheets = ElementTree.SubElement(workbook, f"{{{MAIN_NS}}}sheets")
    ElementTree.SubElement(
        sheets,
        f"{{{MAIN_NS}}}sheet",
        {"name": "检查员库", "sheetId": "1", f"{{{REL_NS}}}id": "rId1"},
    )
    workbook_rels = ElementTree.Element(f"{{{PACKAGE_REL_NS}}}Relationships")
    ElementTree.SubElement(
        workbook_rels,
        f"{{{PACKAGE_REL_NS}}}Relationship",
        {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": "worksheets/sheet1.xml"},
    )

    files = {
        "[Content_Types].xml": _xml_bytes(content_types),
        "_rels/.rels": _xml_bytes(package_rels),
        "xl/workbook.xml": _xml_bytes(workbook),
        "xl/_rels/workbook.xml.rels": _xml_bytes(workbook_rels),
        "xl/worksheets/sheet1.xml": _worksheet(columns, values),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


__all__ = ["build_inspector_query_workbook"]
