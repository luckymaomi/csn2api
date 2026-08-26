from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


ELIGIBLE_CATEGORY = "DOC/official-document"


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


@dataclass(frozen=True)
class WaitingRecord:
    file_id: str
    title: str
    file_type_id: str
    step_item_id: str
    main_category_code: str
    sub_category_code: str
    sub_category_name: str

    @property
    def category(self) -> str:
        return f"{self.main_category_code}/{self.sub_category_code}"

    @property
    def eligible(self) -> bool:
        return self.category == ELIGIBLE_CATEGORY

    @classmethod
    def from_payload(cls, payload: object) -> "WaitingRecord":
        if not isinstance(payload, dict):
            raise ValueError("待办记录结构不是对象")
        record = cls(
            clean_text(payload.get("fileId")), clean_text(payload.get("fileTitle")),
            clean_text(payload.get("fileTypeId")), clean_text(payload.get("stepItemId")),
            clean_text(payload.get("moduleMainCategoryCode")), clean_text(payload.get("moduleSubCategoryCode")),
            clean_text(payload.get("moduleSubCategoryName")),
        )
        if not record.file_id or not record.title:
            raise ValueError("待办记录缺少内部标识或标题")
        if not record.main_category_code or not record.sub_category_code:
            raise ValueError("待办记录缺少模块分类")
        if record.eligible and (not record.file_type_id or not record.step_item_id):
            raise ValueError("公文待办缺少已阅所需字段")
        return record

    def public_result(self, status: str, message: str) -> dict[str, object]:
        return {"title": self.title, "category": self.category, "categoryName": self.sub_category_name, "status": status, "message": message}


@dataclass(frozen=True)
class ScanSnapshot:
    records: list[WaitingRecord]
    total: int

    @classmethod
    def from_records(cls, records: list[WaitingRecord], total: int | None = None) -> "ScanSnapshot":
        return cls(list(records), len(records) if total is None else int(total))

    @property
    def eligible_count(self) -> int:
        return sum(record.eligible for record in self.records)

    @property
    def skipped_count(self) -> int:
        return len(self.records) - self.eligible_count

    def public_categories(self) -> list[dict[str, object]]:
        counts = Counter(record.category for record in self.records)
        samples = {category: next(record for record in self.records if record.category == category) for category in counts}
        return [{
            "category": category, "categoryName": samples[category].sub_category_name, "count": count,
            "action": "已阅" if category == ELIGIBLE_CATEGORY else "跳过",
            "eligible": category == ELIGIBLE_CATEGORY, "sampleTitle": samples[category].title,
        } for category, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
