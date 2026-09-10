from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_QUALIFICATION_CODES = (
    "RAMA", "REUO", "RWAS", "RSEA", "EAMA", "EEUO", "EWAS",
    "ESEA", "RANC", "RORD", "RJFK", "RLAX", "RNLU",
)
DEFAULT_ACTIVE_STATUSES = ("ZAIZHI", "WAIBU", "TUIXIU", "LIZHI")
CAP_TECHNICAL_LEVELS = (
    "CAPZ", "CAPA", "CAPB", "CAPC", "CAPD", "CAPR", "CAPS",
    "RCAP", "CAPTA", "CAPTB", "CAPTC", "CAPE", "CAPF",
)
FO_TECHNICAL_LEVELS = ("FOA1", "FOA2", "FOB", "FOC", "FOD", "FOE")
TECHNICAL_LEVEL_ALIASES = {
    "CAP": CAP_TECHNICAL_LEVELS,
    "FO": FO_TECHNICAL_LEVELS,
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _values(value: object) -> list[str]:
    source = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in source:
        normalized = _text(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def expand_technical_levels(value: object) -> list[str]:
    """Expand friendly technical-level aliases into portal option values."""
    expanded: list[str] = []
    for item in _values(value):
        candidates = TECHNICAL_LEVEL_ALIASES.get(item.upper(), (item,))
        for candidate in candidates:
            if candidate not in expanded:
                expanded.append(candidate)
    return expanded


@dataclass(frozen=True)
class SelectOption:
    value: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"value": self.value, "label": self.label}


@dataclass(frozen=True)
class FilterField:
    name: str
    label: str
    multiple: bool
    options: list[SelectOption]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "multiple": self.multiple,
            "options": [option.to_dict() for option in self.options],
        }


@dataclass(frozen=True)
class OperatingQualification:
    code: str
    name: str
    short_name: str = ""
    type_code: str = ""
    type_name: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "name": self.name,
            "shortName": self.short_name,
            "typeCode": self.type_code,
            "typeName": self.type_name,
            "defaultSelected": self.code in DEFAULT_QUALIFICATION_CODES,
        }


@dataclass(frozen=True)
class QueryFilters:
    person_name: str = ""
    primary_base: str = ""
    operating_base: str = ""
    technical_base: str = ""
    fleet_codes: list[str] = field(default_factory=lambda: ["777"])
    multi_qualification: str = ""
    technical_levels: list[str] = field(default_factory=list)
    help_flying: str = ""
    instructor_checker: str = ""
    active_statuses: list[str] = field(default_factory=lambda: list(DEFAULT_ACTIVE_STATUSES))
    branch: str = ""
    deviation: bool = False

    @classmethod
    def from_payload(cls, payload: object) -> "QueryFilters":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            person_name=_text(data.get("personName")),
            primary_base=_text(data.get("primaryBaseArray")),
            operating_base=_text(data.get("baseArray")),
            technical_base=_text(data.get("techBase")),
            fleet_codes=_values(data.get("fleetCdToArray")),
            multi_qualification=_text(data.get("bolMultiQualCd")),
            technical_levels=expand_technical_levels(data.get("qualTypeArray")),
            help_flying=_text(data.get("bolPriBase")),
            instructor_checker=_text(data.get("bolJCY")),
            active_statuses=_values(data.get("activeStatusArray")),
            branch=_text(data.get("fleetCdbranch")),
            deviation=bool(data.get("isPl")),
        )


def qualifications_from_payload(value: object) -> list[str]:
    return _values(value)
