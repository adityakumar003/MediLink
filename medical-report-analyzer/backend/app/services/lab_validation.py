"""
Deterministic laboratory value classification against report-supplied ranges.

Python is the authority for numerical status. The LLM may explain results
but must not override these classifications.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

# Frontend-compatible statuses (do not send BELOW RANGE / ABOVE RANGE to the API).
STATUS_LOW = "Low"
STATUS_NORMAL = "Normal"
STATUS_HIGH = "High"
STATUS_UNKNOWN = "Unknown"

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")
_OCR_AMBIGUOUS_RE = re.compile(
    r"(?:\?|~|\bill\b|\bunreadable\b|\billegible\b|\bna\b|\bn/?a\b|\bxxx+\b)",
    re.IGNORECASE,
)
_UNIT_RE = re.compile(
    r"(g/dl|mg/dl|mmol/l|µiu/ml|uiu/ml|iu/l|u/l|ng/ml|pg/ml|%"
    r"|10\^3/?[µu]l|10\^9/l|fl|pg|mmhg|/µl|/ul|meq/l|ml/min)",
    re.IGNORECASE,
)

# Interval like "12.0 - 15.5" or "70–100"
_INTERVAL_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)")
_LESS_RE = re.compile(r"[<≤]\s*(-?\d+(?:\.\d+)?)")
_GREATER_RE = re.compile(r"[>≥]\s*(-?\d+(?:\.\d+)?)")

_LAB_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()/%+.-]{1,60}?)\s*[:=]?\s+"
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z%/0-9^.-]{0,20})"
    r"(?:\s+(?P<range>(?:[<≤>≥]\s*)?\d+(?:\.\d+)?(?:\s*[-–]\s*\d+(?:\.\d+)?)?))?",
    re.IGNORECASE,
)


def _normalize_unit(unit: str) -> str:
    return (
        unit.strip()
        .lower()
        .replace("µ", "u")
        .replace(" ", "")
        .replace("^", "")
    )


def extract_unit(text: str) -> str:
    """Return the first recognised unit token in text, or empty string."""
    if not text:
        return ""
    match = _UNIT_RE.search(text)
    return match.group(0) if match else ""


def is_ocr_ambiguous(text: str) -> bool:
    """True when OCR uncertainty markers or conflicting numbers are present."""
    if not text:
        return False
    if _OCR_AMBIGUOUS_RE.search(text):
        return True
    # Ignore numbers that belong to recognised units (e.g. the "3" in 10^3/uL).
    cleaned = _UNIT_RE.sub(" ", text)
    numbers = _NUMBER_RE.findall(cleaned)
    # A value field with several disconnected numbers is unreliable.
    if len(numbers) >= 3 and not _INTERVAL_RE.search(cleaned):
        return True
    return False


def parse_numeric_value_and_range(
    value_str: str, range_str: str
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Extract numeric value and numeric lower/upper bounds.
    Returns: (value_float, lower_bound, upper_bound)
    """
    val_num: Optional[float] = None
    lower: Optional[float] = None
    upper: Optional[float] = None

    val_match = _NUMBER_RE.search(value_str or "")
    if val_match:
        try:
            val_num = float(val_match.group(0))
        except ValueError:
            pass

    if range_str:
        less_match = _LESS_RE.search(range_str)
        if less_match:
            try:
                upper = float(less_match.group(1))
            except ValueError:
                pass

        greater_match = _GREATER_RE.search(range_str)
        if greater_match:
            try:
                lower = float(greater_match.group(1))
            except ValueError:
                pass

        interval_match = _INTERVAL_RE.search(range_str)
        if interval_match:
            try:
                lower = float(interval_match.group(1))
                upper = float(interval_match.group(2))
            except ValueError:
                pass

    return val_num, lower, upper


def units_are_incompatible(value_str: str, range_str: str) -> bool:
    """True when both sides declare a unit and the units do not match."""
    value_unit = _normalize_unit(extract_unit(value_str))
    range_unit = _normalize_unit(extract_unit(range_str or ""))
    if not value_unit or not range_unit:
        return False
    return value_unit != range_unit


def classify_numerical_status(
    val_num: Optional[float],
    lower: Optional[float],
    upper: Optional[float],
    model_classification: str = "",
) -> str:
    """
    Classify using Python numerical rules. Model text is ignored when numbers
    and a usable range are present. Missing or invalid inputs return Unknown.
    """
    del model_classification  # Model must not override validated status.

    if val_num is None:
        return STATUS_UNKNOWN
    if lower is None and upper is None:
        return STATUS_UNKNOWN
    if lower is not None and upper is not None and lower > upper:
        return STATUS_UNKNOWN

    if lower is not None and upper is not None:
        if val_num < lower:
            return STATUS_LOW
        if val_num > upper:
            return STATUS_HIGH
        return STATUS_NORMAL
    if upper is not None:
        return STATUS_HIGH if val_num > upper else STATUS_NORMAL
    return STATUS_LOW if val_num < lower else STATUS_NORMAL  # type: ignore[operator]


def classify_lab_result(value_str: str, range_str: str = "", model_classification: str = "") -> str:
    """
    Full classification from raw report strings, including OCR and unit checks.
    """
    if is_ocr_ambiguous(value_str) or is_ocr_ambiguous(range_str):
        return STATUS_UNKNOWN
    if units_are_incompatible(value_str, range_str):
        return STATUS_UNKNOWN
    if not (value_str or "").strip():
        return STATUS_UNKNOWN

    val_num, lower, upper = parse_numeric_value_and_range(value_str, range_str)
    return classify_numerical_status(val_num, lower, upper, model_classification)


def extract_validated_rows(extracted_text: str) -> list[dict]:
    """Best-effort parse of obvious lab rows for an authoritative prompt prefix."""
    rows: list[dict] = []
    seen: set[str] = set()
    for raw_line in extracted_text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line or line.startswith("--- Page"):
            continue
        match = _LAB_LINE_RE.match(line)
        if not match:
            continue
        name = match.group("name").strip(" :-")
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        value = match.group("value")
        unit = (match.group("unit") or "").strip()
        range_str = (match.group("range") or "").strip()
        value_str = f"{value} {unit}".strip()
        status = classify_lab_result(value_str, range_str)
        rows.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "reference_range": range_str,
                "status": status,
            }
        )
        if len(rows) >= 40:
            break
    return rows


def build_validated_context_block(extracted_text: str) -> str:
    """Prefix the LLM input with Python-validated classifications."""
    rows = extract_validated_rows(extracted_text)
    if not rows:
        return extracted_text
    lines = [
        "[Validated classifications — authoritative. Explain these in plain language.",
        "Do not contradict the classification. Do not invent tests or values.]",
    ]
    for row in rows:
        range_part = f" vs {row['reference_range']}" if row["reference_range"] else " (no reference range)"
        lines.append(
            f"- {row['name']}: {row['value']} {row['unit']}{range_part} → {row['status']}"
        )
    lines.append("")
    lines.append("Laboratory report text:")
    lines.append(extracted_text)
    return "\n".join(lines)


# Canonical test-name aliases: variant substring (lowercase) -> canonical key.
# Used to match extracted names ("Hb", "FPG", "LDL (Bad) Cholesterol") to the
# same clinical concept. Original names are always preserved in output.
# ORDER MATTERS: more specific variants must precede generic ones
# ("hba1c" before " hb", "ldl"/"hdl" before "cholesterol").
_TEST_NAME_ALIASES = {
    "hemoglobin": "hemoglobin",
    "hgb": "hemoglobin",
    "hematocrit": "hematocrit",
    "hct": "hematocrit",
    "rbc": "rbc",
    "red blood cell": "rbc",
    "mcv": "mcv",
    "mchc": "mchc",
    "mch": "mch",
    "rdw": "rdw",
    "platelet": "platelet",
    "wbc": "wbc",
    "white blood": "wbc",
    "hba1c": "hba1c",
    "a1c": "hba1c",
    "fpg": "glucose",
    "fasting plasma": "glucose",
    "blood sugar": "glucose",
    "glucose": "glucose",
    " hb": "hemoglobin",
    "creatinine": "creatinine",
    "egfr": "egfr",
    "gfr": "egfr",
    "bun": "bun",
    "urea": "bun",
    "uric acid": "uric acid",
    "albumin-creatinine ratio": "albumin-creatinine ratio",
    "microalbumin": "albumin-creatinine ratio",
    "albumin": "albumin",
    "acr": "albumin-creatinine ratio",
    "ldl": "ldl cholesterol",
    "hdl": "hdl cholesterol",
    "cholesterol": "cholesterol",
    "triglyceride": "triglycerides",
    "systolic": "systolic blood pressure",
    "diastolic": "diastolic blood pressure",
    "blood pressure": "blood pressure",
    "vitamin b12": "vitamin b12",
    "folate": "folate",
    "ferritin": "ferritin",
    "iron": "iron",
}


def normalize_test_name(name: str) -> str:
    """Return the canonical key for a test name variant (lowercase)."""
    lowered = f" {(name or '').strip().lower()}"
    for variant, canonical in _TEST_NAME_ALIASES.items():
        if variant in lowered:
            return canonical
    return (name or "").strip().lower()


# Aliases used by older tests / hf_space_service.
_parse_numeric_value_and_range = parse_numeric_value_and_range
_classify_numerical_status = classify_numerical_status
