"""
app/services/risk_assessment.py
─────────────────────────────────
Deterministic preliminary disease-risk assessment engine.

Responsibilities (and limits):
- Consumes validated laboratory parameters (statuses from lab_validation).
- Emits explicit assessment states per condition — never a diagnosis and
  never a fabricated probability or severity score.
- A risk *level* is returned only when a documented, adequate marker set
  supports it. Otherwise the state is insufficient_data / not_assessed /
  requires_review with the evidence, missing inputs, method, and guidance.
- Also provides the deterministic fallback summary and the LLM-summary
  consistency check. No LLM is invoked here, ever.

Clinical grounding (informational decision support, not validated models):
- Diabetes: single abnormal glycemic marker -> requires_review (needs
  fasting-status confirmation and repeat/confirmatory testing, e.g. ADA
  guidance that diagnosis requires confirmatory testing). No thresholds
  invented beyond the report's own printed ranges.
- CKD: a formal assessment needs eGFR, albuminuria (ACR), and persistence
  over time (KDIGO-style criteria). A single report cannot establish
  persistence, so this engine never returns "assessed" for CKD: abnormal
  renal markers -> requires_review, otherwise insufficient_data. A lone
  normal creatinine explicitly does NOT support a Low CKD claim.
- Anemia: low hemoglobin (or abnormal red-cell indices) -> requires_review
  (needs iron/B12/bleeding workup context). Adequate normal set
  (hemoglobin + at least one red-cell index) -> assessed Low. Lone normal
  hemoglobin -> insufficient_data (not a comprehensive anemia assessment).
- Cardiovascular: no validated calculator is implemented (established
  calculators need age, sex, smoking, diabetes, and treatment history, and
  apply to specific age ranges). Abnormal lipid/BP markers ->
  requires_review; otherwise insufficient_data. Total cholesterol alone
  never produces an overall risk category.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.lab_validation import normalize_test_name

# Assessment states (also used in API responses and the frontend).
STATE_ASSESSED = "assessed"
STATE_INSUFFICIENT_DATA = "insufficient_data"
STATE_NOT_ASSESSED = "not_assessed"
STATE_REQUIRES_REVIEW = "requires_review"

_LEVEL_LOW = "Low Risk"

_ABNORMAL = {"Low", "High", "Critical"}


def model_flag_to_status(flag_text: str) -> Optional[str]:
    """Map a model/report classification word to the validated status scale."""
    normalized = (flag_text or "").strip().upper()
    if "BELOW" in normalized or normalized == "LOW":
        return "Low"
    if "ABOVE" in normalized or normalized == "HIGH":
        return "High"
    if "WITHIN" in normalized or normalized == "NORMAL":
        return "Normal"
    if "CRITICAL" in normalized:
        return "Critical"
    return None


def find_parameters(
    parameters: List[Dict[str, Any]], *concepts: str
) -> List[Dict[str, Any]]:
    """Return parameters whose normalized identity matches any concept."""
    matched: List[Dict[str, Any]] = []
    for param in parameters:
        if not isinstance(param, dict) or not param.get("name") or "value" not in param:
            continue  # malformed row (e.g. unvalidated third-party output)
        identity = normalize_test_name(str(param.get("name", "")))
        if any(concept in identity for concept in concepts):
            matched.append(param)
    return matched


def _describe(param: Dict[str, Any]) -> str:
    name = param.get("name", "Unknown test")
    value = param.get("value", "?")
    unit = f" {param['unit']}" if param.get("unit") else ""
    ref = f" (reference {param['reference_range']})" if param.get("reference_range") else ""
    return f"{name}: {value}{unit}{ref} [{param.get('status', 'Unknown')}]"


def _abnormal(params: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [p for p in params if p.get("status") in _ABNORMAL]


def assess_diabetes(parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Glycemic markers: HbA1c plus any glucose variant."""
    markers = find_parameters(parameters, "hba1c", "glucose")
    if not markers:
        return {
            "state": STATE_INSUFFICIENT_DATA,
            "level": None,
            "reason": "No glucose or HbA1c tests found in the report.",
            "evidence": [],
            "missing": ["A glucose or HbA1c result with its reference range."],
            "method": None,
            "guidance": "A diabetes assessment needs glycemic markers before any interpretation.",
        }
    bad = _abnormal(markers)
    if bad:
        evidence = [_describe(p) for p in bad]
        return {
            "state": STATE_REQUIRES_REVIEW,
            "level": None,
            "reason": (
                "Abnormal glycemic marker(s) found. This is not a diabetes "
                "diagnosis: fasting status is unconfirmed and guidelines require "
                "confirmatory testing."
            ),
            "evidence": evidence,
            "missing": [
                "Confirmation that the sample was fasting (where relevant).",
                "Repeat or confirmatory testing (e.g. HbA1c / repeat glucose).",
            ],
            "method": "Single-marker range review of available glycemic markers.",
            "guidance": "Discuss with a clinician; do not diagnose diabetes from one value.",
        }
    # Adequate for a cautious "no abnormality" statement: HbA1c, or a
    # glucose reading explicitly labelled as fasting. Anything else normal
    # cannot rule dysglycemia in or out.
    adequate = any(
        normalize_test_name(str(p.get("name", ""))) == "hba1c"
        or "fast" in str(p.get("name", "")).lower()
        for p in markers
        if normalize_test_name(str(p.get("name", ""))) in {"hba1c", "glucose"}
    )
    if adequate:
        return {
            "state": STATE_ASSESSED,
            "level": _LEVEL_LOW,
            "reason": "Available glycemic marker(s) are within their printed ranges.",
            "evidence": [_describe(p) for p in markers],
            "missing": [],
            "method": "Single-marker range review (not a comprehensive diabetes assessment).",
            "guidance": "A normal single reading does not rule out dysglycemia; interpret clinically.",
        }
    return {
        "state": STATE_INSUFFICIENT_DATA,
        "level": None,
        "reason": "Available glucose readings lack fasting context or HbA1c support.",
        "evidence": [_describe(p) for p in markers],
        "missing": ["Fasting-status confirmation or an HbA1c result."],
        "method": None,
        "guidance": "A formal assessment needs fasting context or HbA1c.",
    }


def assess_ckd(parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Kidney markers: creatinine, eGFR, BUN/urea, albumin/ACR.

    Persistence over time can never be established from a single report,
    so this engine never returns "assessed" for CKD.
    """
    markers = find_parameters(
        parameters, "creatinine", "egfr", "bun", "uric acid", "albumin", "albumin-creatinine ratio"
    )
    if not markers:
        return {
            "state": STATE_INSUFFICIENT_DATA,
            "level": None,
            "reason": "No renal function indicators (e.g. Creatinine, eGFR, BUN) found in the report.",
            "evidence": [],
            "missing": ["Creatinine/eGFR and urine albumin (ACR) results."],
            "method": None,
            "guidance": "Kidney assessment needs renal markers before any interpretation.",
        }
    bad = _abnormal(markers)
    if bad:
        return {
            "state": STATE_REQUIRES_REVIEW,
            "level": None,
            "reason": (
                "Abnormal renal marker(s) found. Kidney injury or CKD can only "
                "be established with eGFR, albuminuria, and persistence over time."
            ),
            "evidence": [_describe(p) for p in bad],
            "missing": [
                "eGFR value.",
                "Urine albumin-to-creatinine ratio (ACR).",
                "Repeat testing over time to establish persistence.",
            ],
            "method": "Single-marker range review of available renal markers.",
            "guidance": "Discuss with a clinician; a single abnormal value is not a CKD diagnosis.",
        }
    return {
        "state": STATE_INSUFFICIENT_DATA,
        "level": None,
        "reason": (
            "Available renal markers are normal, but a CKD assessment cannot be "
            "completed: it requires eGFR, albuminuria, and persistence over time."
        ),
        "evidence": [_describe(p) for p in markers],
        "missing": [
            "eGFR value.",
            "Urine albumin-to-creatinine ratio (ACR).",
            "Evidence of persistence over time.",
        ],
        "method": None,
        "guidance": "Normal creatinine alone does not rule out kidney disease.",
    }


def assess_anemia(parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Red-cell markers: hemoglobin plus indices (MCV/MCH/RBC/Hct/iron...)."""
    markers = find_parameters(
        parameters, "hemoglobin", "hematocrit", "rbc", "mcv", "mch", "rdw",
        "iron", "ferritin", "vitamin b12", "folate",
    )
    if not markers:
        return {
            "state": STATE_INSUFFICIENT_DATA,
            "level": None,
            "reason": "No red blood cell or hemoglobin indicators found in the report.",
            "evidence": [],
            "missing": ["Hemoglobin and red-cell indices (e.g. MCV, RBC)."],
            "method": None,
            "guidance": "Anemia assessment needs red-cell markers before any interpretation.",
        }
    bad = _abnormal(markers)
    if bad:
        return {
            "state": STATE_REQUIRES_REVIEW,
            "level": None,
            "reason": (
                "Abnormal red-cell marker(s) found. The cause (iron, B12, "
                "blood loss, chronic disease) needs clinical workup."
            ),
            "evidence": [_describe(p) for p in bad],
            "missing": [
                "Iron studies / ferritin, B12/folate where indicated.",
                "Clinical context (bleeding, diet, chronic disease).",
            ],
            "method": "Single-marker range review of available red-cell markers.",
            "guidance": "Discuss with a clinician; do not self-supplement iron without workup.",
        }
    indices = find_parameters(
        parameters, "hematocrit", "rbc", "mcv", "mch", "rdw", "iron", "ferritin"
    )
    if indices:
        return {
            "state": STATE_ASSESSED,
            "level": _LEVEL_LOW,
            "reason": "Hemoglobin and supporting red-cell indices are within their printed ranges.",
            "evidence": [_describe(p) for p in markers],
            "missing": [],
            "method": "Hemoglobin with red-cell index review (not a comprehensive anemia workup).",
            "guidance": "Normal indices do not exclude every cause of anemia; interpret clinically.",
        }
    return {
        "state": STATE_INSUFFICIENT_DATA,
        "level": None,
        "reason": (
            "Hemoglobin is within range, but no supporting red-cell indices "
            "are available, so a comprehensive anemia assessment is not possible."
        ),
        "evidence": [_describe(p) for p in markers],
        "missing": ["Red-cell indices (MCV, MCH, RBC, hematocrit) or iron studies."],
        "method": None,
        "guidance": "A lone normal hemoglobin is not a comprehensive anemia assessment.",
    }


def assess_cardiovascular(parameters: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lipid/BP markers. No validated 10-year risk calculator is implemented
    (established calculators need age, sex, smoking, diabetes, and treatment
    history in specific age ranges), so this engine never returns "assessed".
    """
    markers = find_parameters(
        parameters, "cholesterol", "ldl cholesterol", "hdl cholesterol",
        "triglycerides", "blood pressure",
    )
    # Avoid double-counting "cholesterol" substrings already covered by ldl/hdl.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for p in markers:
        pid = id(p)
        if pid not in seen:
            seen.add(pid)
            unique.append(p)
    markers = unique
    if not markers:
        return {
            "state": STATE_INSUFFICIENT_DATA,
            "level": None,
            "reason": "No lipid panel or cardiovascular indicators found in the report.",
            "evidence": [],
            "missing": ["Lipid panel and blood pressure readings."],
            "method": None,
            "guidance": "Cardiovascular review needs lipid/BP data before any interpretation.",
        }
    bad = _abnormal(markers)
    if bad:
        return {
            "state": STATE_REQUIRES_REVIEW,
            "level": None,
            "reason": (
                "Abnormal lipid or blood-pressure marker(s) found. No overall "
                "cardiovascular risk category is calculated from these alone."
            ),
            "evidence": [_describe(p) for p in bad],
            "missing": [
                "Age, sex, smoking status, diabetes status, and treatment history "
                "required by validated risk calculators.",
                "Confirmation that the patient meets a calculator's eligibility criteria.",
            ],
            "method": "Single-marker range review (no validated risk calculator implemented).",
            "guidance": "Discuss with a clinician; total cholesterol alone never defines overall risk.",
        }
    return {
        "state": STATE_INSUFFICIENT_DATA,
        "level": None,
        "reason": (
            "Available lipid/BP markers are normal, but 10-year cardiovascular "
            "risk cannot be calculated without a validated calculator's inputs."
        ),
        "evidence": [_describe(p) for p in markers],
        "missing": [
            "Age, sex, smoking status, diabetes status, and treatment history.",
            "A validated risk calculator applicable to the patient.",
        ],
        "method": None,
        "guidance": "Normal lipids on one panel do not equal low long-term cardiovascular risk.",
    }


def legacy_risk_item(key: str, disease_risks_raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map a stored disease-risk dict (including pre-state legacy reports
    that only carry level/reason) to the current assessment shape."""
    item = disease_risks_raw.get(key, {}) or {}
    level = item.get("level")
    state = item.get("state")
    if not state:
        state = STATE_INSUFFICIENT_DATA if level in (None, "Insufficient Data") else STATE_ASSESSED
    return {
        "level": level,
        "reason": item.get("reason", ""),
        "state": state,
        "evidence": item.get("evidence", []),
        "missing": item.get("missing", []),
        "method": item.get("method"),
        "guidance": item.get("guidance", ""),
    }


def derive_disease_risks(parameters: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Single source of truth for all providers (HF, Gemini, offline).

    Returns per-condition dicts with: state, level (only when assessed),
    reason, evidence, missing, method, guidance.
    """
    return {
        "diabetes": assess_diabetes(parameters),
        "ckd": assess_ckd(parameters),
        "anemia": assess_anemia(parameters),
        "cardiovascular": assess_cardiovascular(parameters),
    }


# ── Deterministic summary + LLM consistency guard ──────────────────────────

_CONTRADICTION_PATTERNS = (
    r"all\s+(results|values|tests|parameters)\s+are\s+(within|in)\s+normal",
    r"every\s+(result|value|test)\s+(is\s+)?(within|in)\s+normal",
    r"everything\s+is\s+normal",
    r"nothing\s+abnormal",
    r"no\s+abnormal\w*\s+(finding|result|value)",
)


def build_template_summary(parameters: List[Dict[str, Any]]) -> str:
    """Deterministic doctor-facing summary used when the LLM is off or its
    summary contradicts validated statuses."""
    abnormal = [p for p in parameters if p.get("status") in _ABNORMAL]
    if not parameters:
        return (
            "The report text was extracted successfully, but no measurable "
            "laboratory rows were identified. A clinician should verify the "
            "report directly."
        )
    if not abnormal:
        return (
            f"The report text was extracted successfully and {len(parameters)} "
            "laboratory row(s) were validated locally against their printed "
            "reference ranges; all classifiable results are within range. "
            "A clinician should verify all values and interpretation."
        )
    names = ", ".join(
        f"{p['name']} ({p['value']} {p.get('unit', '')})".strip() for p in abnormal
    )
    return (
        f"The report text was extracted successfully and {len(parameters)} "
        f"laboratory row(s) were validated locally. {len(abnormal)} result(s) "
        f"outside their printed reference ranges require clinician review: "
        f"{names}. A clinician should verify all values and interpretation."
    )


def ensure_consistent_summary(
    summary: str, parameters: List[Dict[str, Any]]
) -> str:
    """Replace an LLM summary that contradicts validated abnormal findings
    with the deterministic template. Returns the original when consistent.
    """
    abnormal = [p for p in parameters if p.get("status") in _ABNORMAL]
    if not abnormal or not summary:
        return summary
    lowered = summary.lower()
    if any(re.search(pattern, lowered) for pattern in _CONTRADICTION_PATTERNS):
        return build_template_summary(parameters)
    return summary
