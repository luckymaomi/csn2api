from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any


CAAC_TIMEZONE = timezone(timedelta(hours=8))

FIELD_LABELS = {
    "pilotId": "飞行员ID",
    "pilotname": "姓名",
    "pilotnameeng": "英文姓名",
    "country": "国籍",
    "idType": "证件类型",
    "idCode": "证件号码",
    "sex": "性别",
    "birthday": "出生日期",
    "medicalBirthday": "出生日期",
    "birthplace": "出生地",
    "nation": "民族",
    "mobile": "手机号码",
    "mailaddr": "通信地址",
    "zipcode": "邮政编码",
    "chineseOrg": "所属单位",
    "address": "单位地址",
    "regionName": "所属地区",
    "archiveNo": "档案号",
    "licenseNo": "执照编号",
    "licenseTypeName": "执照类型",
    "nameCn": "执照类型",
    "licenseStatus": "执照状态",
    "englishLevel": "英语语言等级",
    "validDate": "英语语言等级有效期",
    "chineseLevel": "汉语语言等级",
    "chineseLevelValidDate": "汉语语言等级有效期",
    "licenseLimit": "执照限制",
    "degree": "学历",
    "medicalno": "体检合格证编号",
    "expDate": "执照有效期",
    "enddate": "体检合格证有效期",
    "copType": "副驾驶类别",
    "pilotgrade": "飞行员等级",
}

HIDDEN_TOP_LEVEL_FIELDS = {
    "pilotPhotoFileUrl",
    "pilotIdFileUrl",
    "pilotDegreeFileUrl",
}


@dataclass(frozen=True)
class RecordSpec:
    label: str
    fields: dict[str, str]
    hidden: frozenset[str]


COMMON_AUDIT_FIELDS = frozenset({
    "creationBy",
    "creationDate",
    "updateBy",
    "updateDate",
    "validFlag",
    "eindex",
    "pilotId",
})

RECORD_SPECS = {
    "educationList": RecordSpec(
        "教育经历",
        {
            "school": "学校",
            "college": "院系",
            "major": "专业",
            "degree": "学历或学位",
            "startDate": "开始日期",
            "endDate": "结束日期",
        },
        COMMON_AUDIT_FIELDS | {"eduId"},
    ),
    "workexps": RecordSpec(
        "工作经历",
        {
            "organization": "工作单位",
            "location": "工作地点",
            "title": "职务",
            "startDate": "开始日期",
            "endDate": "结束日期",
        },
        COMMON_AUDIT_FIELDS | {"workExpId"},
    ),
    "jzhxinfos": RecordSpec(
        "机长航线检查记录",
        {
            "CHECKDATE": "检查日期",
            "CHECKLINE": "检查航线",
            "EXAMINER": "检查员",
            "LASTEXPDATE": "上次到期日期",
            "RESULT": "检查结果",
        },
        frozenset({"CHECK_ID"}),
    ),
    "yjscinfos": RecordSpec(
        "应急生存训练记录",
        {
            "CHECKDATE": "检查日期",
            "CHECKPLACE": "检查地点",
            "LASTEXPDATE": "上次到期日期",
            "RESULT": "检查结果",
        },
        frozenset({"CHECK_ID"}),
    ),
    "printhis": RecordSpec(
        "执照打印历史",
        {
            "PRINTDATE": "打印日期",
            "PRINTREASON": "打印原因",
            "USERNAME": "操作人",
        },
        frozenset(),
    ),
    "printList": RecordSpec(
        "执照打印记录",
        {
            "printDate": "打印日期",
            "printReason": "打印原因",
            "printStatus": "打印状态",
            "agreeUser": "审批人",
            "agreeDate": "审批日期",
        },
        COMMON_AUDIT_FIELDS | {"printId", "licenseId"},
    ),
    "checkpcinfos": RecordSpec(
        "熟练检查记录",
        {
            "ACMODEL": "航空器型号",
            "BASEMONTH": "基准月",
            "CHECKDATE": "检查日期",
            "CHECKTYPE": "检查类型",
            "EXAMINER": "检查员",
            "LASTEXPDATE": "上次到期日期",
            "NEXTDATE": "下次检查日期",
            "NEXTEXPDATE": "下次到期日期",
            "NEXT_MONTH": "下次检查月份",
            "NOTES": "备注",
            "RESULT": "检查结果",
        },
        frozenset({"ACMODELID", "PCID"}),
    ),
}


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if 100_000_000_000 <= abs(value) <= 100_000_000_000_000:
            try:
                return datetime.fromtimestamp(value / 1000, CAAC_TIMEZONE).date().isoformat()
            except (OSError, OverflowError, ValueError):
                pass
        return str(value)
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?i)</?br\s*/?>", "\n", unescape(text))
    return text.strip()


def _tree_lines(value: Any, depth: int = 0) -> list[str]:
    if isinstance(value, list):
        lines: list[str] = []
        for item in value:
            lines.extend(_tree_lines(item, depth))
        return lines
    if isinstance(value, dict):
        label = _scalar(value.get("layerinfo") or value.get("name") or value.get("title"))
        own = [("  " * depth) + label] if label else []
        return own + _tree_lines(value.get("sublayers"), depth + 1)
    return [_scalar(value)] if value not in (None, "") else []


def _unknown_label(key: str) -> str:
    return f"未映射字段（{key}）"


def _nested_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return _scalar(value)


def _record_text(value: Any, spec: RecordSpec) -> str:
    if not isinstance(value, list):
        return _nested_value(value)
    rows: list[str] = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            text = _scalar(item)
            if text:
                rows.append(f"{index}. {text}")
            continue
        parts: list[str] = []
        for key, label in spec.fields.items():
            text = _nested_value(item.get(key))
            if text:
                parts.append(f"{label}：{text}")
        for key, raw in item.items():
            if key in spec.fields or key in spec.hidden:
                continue
            text = _nested_value(raw)
            if text:
                parts.append(f"{_unknown_label(key)}：{text}")
        if parts:
            rows.append(f"{index}. " + "；".join(parts))
    return "\n".join(rows)


def _flatten_scalars(payload: dict[str, Any]) -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, label in FIELD_LABELS.items():
        if key not in payload or isinstance(payload[key], (list, dict)):
            continue
        value = _scalar(payload[key])
        if label not in flattened or not flattened[label]:
            flattened[label] = value
    for key, value in payload.items():
        if key in FIELD_LABELS or key in HIDDEN_TOP_LEVEL_FIELDS or isinstance(value, (list, dict)):
            continue
        flattened[_unknown_label(key)] = _scalar(value)
    return flattened


def flatten_detail(detail: dict[str, Any]) -> dict[str, str]:
    flattened = _flatten_scalars(detail)
    if "layerInfosList" in detail:
        flattened["资质信息"] = "\n".join(_tree_lines(detail["layerInfosList"]))
    for key, value in detail.items():
        if key == "layerInfosList" or not isinstance(value, (list, dict)):
            continue
        spec = RECORD_SPECS.get(key)
        if spec:
            flattened[spec.label] = _record_text(value, spec)
        else:
            flattened[_unknown_label(key)] = _nested_value(value)
    return flattened


def flatten_listing(listing: dict[str, Any]) -> dict[str, str]:
    return _flatten_scalars(listing)
