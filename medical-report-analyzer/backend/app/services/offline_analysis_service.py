"""Conservative report analysis used when AI_MODE=offline.

No LLM is involved: laboratory rows are parsed from the extracted text and
every status is derived deterministically with lab_validation against the
reference range printed on the report. Disease-risk cards are informational
summaries of those validated statuses, not diagnoses.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.lab_validation import classify_lab_result, extract_unit
from app.services.lab_validation import (
    parse_numeric_value_and_range as _parse_bounds,
)
from app.services.risk_assessment import (
    build_template_summary,
    derive_disease_risks,
    model_flag_to_status,
)

# Lenient row match: name, numeric value, optional unit, then anything
# (reference range in any supported shape, optional trailing flag word).
_PARAMETER_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 ()/%+.-]{1,60}?)"
    r"\s*[:=\-]?\s*"
    r"(?P<value>-?\d+(?:\.\d+)?)"
    r"\s*(?P<unit>[A-Za-z/%^0-9.µu-]{0,12})"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)
_TRAILING_FLAG_RE = re.compile(
    r"\b(high|low|normal|critical|abnormal|borderline)\b\s*[.)]?\s*$",
    re.IGNORECASE,
)
_BARE_VALUE_RE = re.compile(
    r"^(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z/%^0-9.µu-]{0,12})$",
    re.IGNORECASE,
)
_TRAILING_PREPOSITION_RE = re.compile(
    r"\s+(at|of|is|was|are|were|with|and|in|on|for|to)$",
    re.IGNORECASE,
)

# Lines that are never test names in column-style lab tables.
_NON_NAME_HEADERS = {
    "test description", "result", "units", "reference range",
    "patient information", "report details", "complete blood",
    "metabolic panel", "clinical observations", "medreport",
}

_MAX_PARAMETERS = 40
# Single-line matches from very long (sentence-like) lines are narrative
# prose, not lab rows — column tables are handled by _extract_table_rows.
_MAX_SINGLE_LINE_LENGTH = 90


def _clean_name(raw: str) -> str:
    name = raw.strip().strip(" :-")
    name = _TRAILING_PREPOSITION_RE.sub("", name).strip()
    return name


def _extract_table_rows(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse column-style tables where name/value/unit/range sit on
    consecutive lines (the way PyMuPDF emits multi-column lab reports).
    """
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    stripped = [" ".join(ln.strip().split()) for ln in lines]

    def is_name_line(text: str) -> bool:
        if not text or text.startswith("--- Page"):
            return False
        if len(text) < 2 or len(text) > 60 or ":" in text:
            return False
        if re.search(r"\d", text):
            return False
        lowered = text.lower()
        if any(lowered.startswith(h) for h in _NON_NAME_HEADERS):
            return False
        return lowered[0].isalpha()

    i = 0
    while i < len(stripped):
        if not is_name_line(stripped[i]):
            i += 1
            continue
        name = _clean_name(stripped[i])
        key = name.lower()
        # Gather the next non-empty lines (value, then unit/range in any order).
        following: List[str] = []
        j = i + 1
        while j < len(stripped) and len(following) < 3:
            if stripped[j] and not stripped[j].startswith("--- Page"):
                following.append(stripped[j])
            j += 1
        if not following:
            i += 1
            continue
        value_match = _BARE_VALUE_RE.match(following[0])
        if not value_match or key in seen:
            i += 1
            continue

        raw_value = value_match.group("value")
        unit = (value_match.group("unit") or "").strip()
        range_candidate, flag = "", ""
        for extra in following[1:3]:
            # A line is a range only if it yields real bounds for this value;
            # unit-only lines (e.g. "10^3/uL") contain digits but no bounds.
            _, low, high = _parse_bounds(f"{raw_value} {unit}".strip(), extra)
            if low is not None or high is not None:
                range_candidate, flag = _clean_range_candidate(extra)
                if not unit:
                    unit = extract_unit(extra)
                break
            if not unit and extract_unit(extra):
                unit = extra.strip()
        try:
            value: int | float = float(raw_value) if "." in raw_value else int(raw_value)
        except ValueError:
            i += 1
            continue

        seen.add(key)
        value_str = f"{raw_value} {unit}".strip()
        reference = range_candidate if re.search(r"\d", range_candidate) else None
        validated = classify_lab_result(value_str, range_candidate, flag)
        model_status = model_flag_to_status(flag)
        rows.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "status": validated,
                "reference_range": reference,
                "report_flag": flag or None,
                "flag_mismatch": bool(model_status) and model_status != validated,
            }
        )
        if len(rows) >= _MAX_PARAMETERS:
            break
        i = j
    return rows


def _clean_range_candidate(rest: str) -> tuple[str, str]:
    """Split trailing text into (range_candidate, flag_word)."""
    text = rest.strip().strip("()[]").strip()
    flag = ""
    paren_flag = re.search(
        r"\(\s*(high|low|normal|critical|abnormal|borderline)\s*\)",
        text,
        re.IGNORECASE,
    )
    if paren_flag:
        flag = paren_flag.group(1).title()
    # Parenthesized flags ("70 - 99 (HIGH)") are report annotations, not
    # part of the reference range itself.
    text = re.sub(
        r"\(\s*(high|low|normal|critical|abnormal|borderline)\s*\)",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip().strip("()[]").strip()
    if not flag:
        flag_match = _TRAILING_FLAG_RE.search(text)
        if flag_match:
            flag = flag_match.group(1).title()
            text = text[: flag_match.start()].strip().strip("()[]").strip()
    return " ".join(text.split()), flag


def _extract_parameters(extracted_text: str) -> List[Dict[str, Any]]:
    lines = extracted_text.splitlines()
    # Column-style tables first (authoritative); single-line rows fill gaps.
    parameters: List[Dict[str, Any]] = _extract_table_rows(lines)
    seen = {p["name"].lower() for p in parameters}

    for raw_line in lines:
        line = " ".join(raw_line.strip().split())
        if not line or line.startswith("--- Page") or len(line) > _MAX_SINGLE_LINE_LENGTH:
            continue
        match = _PARAMETER_LINE_RE.match(line)
        if not match:
            continue

        name = _clean_name(match.group("name"))
        key = name.lower()
        if len(key) < 2 or key in seen:
            continue

        raw_value = match.group("value")
        unit = (match.group("unit") or "").strip()
        range_candidate, flag = _clean_range_candidate(match.group("rest") or "")

        value_str = f"{raw_value} {unit}".strip()
        # Skip junk lines (e.g. dates): require a recognised unit or a
        # parseable reference bound.
        _, lower, upper = _parse_bounds(value_str, range_candidate)
        if not extract_unit(value_str) and lower is None and upper is None:
            continue
        seen.add(key)

        try:
            value: int | float = float(raw_value) if "." in raw_value else int(raw_value)
        except ValueError:
            continue

        reference = range_candidate if re.search(r"\d", range_candidate) else None
        validated = classify_lab_result(value_str, range_candidate, flag)
        model_status = model_flag_to_status(flag)
        parameters.append(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "status": validated,
                "reference_range": reference,
                "report_flag": flag or None,
                "flag_mismatch": bool(model_status) and model_status != validated,
            }
        )
        if len(parameters) >= _MAX_PARAMETERS:
            break
    return parameters


def analyse_report_text_offline(extracted_text: str) -> Dict[str, Any]:
    """Extract and deterministically validate lab rows without an LLM."""
    parameters = _extract_parameters(extracted_text)
    disease_risks = derive_disease_risks(parameters)
    summary = build_template_summary(parameters)
    return {"summary": summary, "parameters": parameters, "disease_risks": disease_risks}
