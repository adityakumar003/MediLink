"""Tests for the deterministic disease-risk assessment engine.

No LLM is involved anywhere in this file. The engine consumes validated
parameter dicts (statuses from lab_validation) and returns explicit
assessment states. External providers are mocked for dispatcher tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.analysis import DiseaseRiskItem
from app.services.lab_validation import normalize_test_name
from app.services.offline_analysis_service import analyse_report_text_offline
from app.services.ollama_service import analyse_report_text
from app.services.risk_assessment import (
    STATE_ASSESSED,
    STATE_INSUFFICIENT_DATA,
    STATE_REQUIRES_REVIEW,
    build_template_summary,
    derive_disease_risks,
    ensure_consistent_summary,
    legacy_risk_item,
    model_flag_to_status,
)


def _param(name: str, value: float, unit: str, status: str, ref: str | None = None):
    return {
        "name": name,
        "value": value,
        "unit": unit,
        "status": status,
        "reference_range": ref,
    }


# ── Phase 9 regression: the current sample report ──────────────────────────

SAMPLE_PARAMS = [
    _param("Fasting Blood Glucose", 108, "mg/dL", "High", "70 - 99 mg/dL"),
    _param("Total Cholesterol", 215, "mg/dL", "High", "< 200 mg/dL"),
    _param("LDL (Bad) Cholesterol", 135, "mg/dL", "High", "< 100 mg/dL"),
    _param("HDL (Good) Cholesterol", 42, "mg/dL", "Normal", "> 40 mg/dL"),
    _param("Triglycerides", 180, "mg/dL", "High", "< 150 mg/dL"),
    _param("Serum Creatinine", 0.9, "mg/dL", "Normal", "0.7 - 1.3 mg/dL"),
    _param("Hemoglobin", 15.2, "g/dL", "Normal", "13.8 - 17.2 g/dL"),
    _param("Systolic Blood Pressure", 128, "mmHg", "High", "< 120 mmHg"),
    _param("Diastolic Blood Pressure", 82, "mmHg", "High", "< 80 mmHg"),
]


def test_sample_report_reassessment() -> None:
    """Phase 9 values re-evaluated: no unsupported Low/Moderate scores."""
    risks = derive_disease_risks(SAMPLE_PARAMS)

    diabetes = risks["diabetes"]
    assert diabetes["state"] == STATE_REQUIRES_REVIEW
    assert diabetes["level"] is None  # not a diagnosis, no categorical score
    assert any("108" in e for e in diabetes["evidence"])
    assert diabetes["missing"]  # fasting confirmation + repeat testing named

    ckd = risks["ckd"]
    assert ckd["state"] == STATE_INSUFFICIENT_DATA
    assert ckd["level"] is None  # lone normal creatinine supports no Low claim

    anemia = risks["anemia"]
    assert anemia["state"] == STATE_INSUFFICIENT_DATA
    assert anemia["level"] is None  # lone normal Hb is not a workup

    cardio = risks["cardiovascular"]
    assert cardio["state"] == STATE_REQUIRES_REVIEW
    assert cardio["level"] is None  # no calculator, no overall category


# ── Per-condition rules ────────────────────────────────────────────────────

def test_elevated_glucose_is_not_a_diagnosis() -> None:
    risks = derive_disease_risks([_param("Glucose", 140, "mg/dL", "High", "70-100")])
    assert risks["diabetes"]["state"] == STATE_REQUIRES_REVIEW
    assert "diagnos" in risks["diabetes"]["reason"].lower()
    assert "confirmatory" in " ".join(risks["diabetes"]["missing"]).lower()


def test_normal_hba1c_supports_assessed_low() -> None:
    risks = derive_disease_risks([_param("HbA1c", 5.4, "%", "Normal", "4.0-5.6")])
    assert risks["diabetes"]["state"] == STATE_ASSESSED
    assert risks["diabetes"]["level"] == "Low Risk"
    assert risks["diabetes"]["method"]


def test_plain_normal_glucose_is_insufficient_without_fasting_context() -> None:
    risks = derive_disease_risks([_param("Glucose", 95, "mg/dL", "Normal", "70-100")])
    assert risks["diabetes"]["state"] == STATE_INSUFFICIENT_DATA


def test_creatinine_only_cannot_assess_ckd() -> None:
    risks = derive_disease_risks([_param("Creatinine", 0.9, "mg/dL", "Normal", "0.6-1.2")])
    assert risks["ckd"]["state"] == STATE_INSUFFICIENT_DATA
    assert risks["ckd"]["level"] is None


def test_abnormal_renal_marker_requires_review_not_diagnosis() -> None:
    risks = derive_disease_risks([_param("Creatinine", 2.1, "mg/dL", "High", "0.6-1.2")])
    ckd = risks["ckd"]
    assert ckd["state"] == STATE_REQUIRES_REVIEW
    assert ckd["level"] is None
    assert any("eGFR" in m or "ACR" in m for m in ckd["missing"])


def test_lone_normal_hemoglobin_makes_no_anemia_claim() -> None:
    risks = derive_disease_risks([_param("Hemoglobin", 15.2, "g/dL", "Normal", "13.8-17.2")])
    anemia = risks["anemia"]
    assert anemia["state"] == STATE_INSUFFICIENT_DATA
    assert anemia["level"] is None


def test_low_hemoglobin_requires_review() -> None:
    risks = derive_disease_risks([_param("Hb", 9.8, "g/dL", "Low", "12.0-15.5")])
    anemia = risks["anemia"]
    assert anemia["state"] == STATE_REQUIRES_REVIEW
    assert anemia["level"] is None


def test_hemoglobin_with_indices_can_be_assessed() -> None:
    risks = derive_disease_risks([
        _param("Hemoglobin", 14.0, "g/dL", "Normal", "12.0-15.5"),
        _param("MCV", 90, "fL", "Normal", "80-100"),
    ])
    anemia = risks["anemia"]
    assert anemia["state"] == STATE_ASSESSED
    assert anemia["level"] == "Low Risk"


def test_cholesterol_alone_never_sets_overall_cardio_category() -> None:
    risks = derive_disease_risks([_param("Total Cholesterol", 260, "mg/dL", "High", "< 200")])
    cardio = risks["cardiovascular"]
    assert cardio["state"] == STATE_REQUIRES_REVIEW
    assert cardio["level"] is None


def test_no_markers_means_insufficient_data_everywhere() -> None:
    risks = derive_disease_risks([])
    for condition in ("diabetes", "ckd", "anemia", "cardiovascular"):
        assert risks[condition]["state"] == STATE_INSUFFICIENT_DATA
        assert risks[condition]["level"] is None
        assert risks[condition]["missing"]


def test_levels_appear_only_when_assessed() -> None:
    """Invariant: level is set iff state == assessed."""
    cases = [
        [],
        [_param("Glucose", 200, "mg/dL", "High", "70-100")],
        [_param("HbA1c", 5.4, "%", "Normal", "4.0-5.6")],
        [_param("Creatinine", 0.9, "mg/dL", "Normal", "0.6-1.2")],
        SAMPLE_PARAMS,
    ]
    for params in cases:
        for item in derive_disease_risks(params).values():
            if item["state"] == STATE_ASSESSED:
                assert item["level"] is not None
            else:
                assert item["level"] is None


# ── Evaluation dataset: normal / borderline / abnormal / incomplete / noisy ─

EVAL_CASES = [
    # (label, params, expected_states_by_condition_subset)
    ("all normal cbc", [_param("Hemoglobin", 14.0, "g/dL", "Normal", "12-16"),
                        _param("MCV", 90, "fL", "Normal", "80-100")],
     {"anemia": STATE_ASSESSED}),
    ("borderline glucose", [_param("Fasting Blood Glucose", 100, "mg/dL", "High", "70-99")],
     {"diabetes": STATE_REQUIRES_REVIEW}),
    ("boundary value", [_param("Glucose", 99, "mg/dL", "Normal", "70-99")],
     {"diabetes": STATE_INSUFFICIENT_DATA}),
    ("missing range", [_param("Glucose", 110, "mg/dL", "Unknown", None)],
     {"diabetes": STATE_INSUFFICIENT_DATA}),
    ("unit mismatch", [_param("Hemoglobin", 10.2, "g/dL", "Unknown", "12.0-15.5 mmol/L")],
     {"anemia": STATE_INSUFFICIENT_DATA}),
    ("ocr ambiguous", [_param("Hemoglobin", "10.?", "g/dL", "Unknown", "12.0-15.5")],
     {"anemia": STATE_INSUFFICIENT_DATA}),
    ("noisy junk rows only", [_param("Date", 2026, "", "Unknown", None)],
     {"diabetes": STATE_INSUFFICIENT_DATA, "ckd": STATE_INSUFFICIENT_DATA}),
    ("full abnormal panel", SAMPLE_PARAMS,
     {"diabetes": STATE_REQUIRES_REVIEW, "ckd": STATE_INSUFFICIENT_DATA,
      "anemia": STATE_INSUFFICIENT_DATA, "cardiovascular": STATE_REQUIRES_REVIEW}),
]


@pytest.mark.parametrize("label,params,expected", EVAL_CASES, ids=[c[0] for c in EVAL_CASES])
def test_eval_dataset(label: str, params: list, expected: dict) -> None:
    risks = derive_disease_risks(params)
    for condition, state in expected.items():
        assert risks[condition]["state"] == state, label


# ── Name normalization ─────────────────────────────────────────────────────

def test_normalize_test_name_variants() -> None:
    assert normalize_test_name("Hb") == "hemoglobin"
    assert normalize_test_name("LDL (Bad) Cholesterol") == "ldl cholesterol"
    assert normalize_test_name("FPG") == "glucose"
    assert normalize_test_name("eGFR") == "egfr"


# ── Report-flag distinction ────────────────────────────────────────────────

def test_model_flag_mapping() -> None:
    assert model_flag_to_status("ABOVE RANGE") == "High"
    assert model_flag_to_status("WITHIN RANGE") == "Normal"
    assert model_flag_to_status("BELOW RANGE") == "Low"
    assert model_flag_to_status("garbage") is None


def test_offline_flag_mismatch_is_recorded() -> None:
    result = analyse_report_text_offline("Hemoglobin: 10.2 g/dL 12.0-15.5 Normal\n")
    param = result["parameters"][0]
    assert param["status"] == "Low"  # validated status wins
    assert param["report_flag"] == "Normal"
    assert param["flag_mismatch"] is True


def test_matching_flag_is_not_a_mismatch() -> None:
    result = analyse_report_text_offline("Hemoglobin: 13.5 g/dL 12.0-15.5 Normal\n")
    param = result["parameters"][0]
    assert param["status"] == "Normal"
    assert param["flag_mismatch"] is False


# ── Summary consistency guard ──────────────────────────────────────────────

def test_contradicting_summary_is_replaced() -> None:
    params = [_param("Glucose", 180, "mg/dL", "High", "70-100")]
    fixed = ensure_consistent_summary(
        "All results are within normal limits. Nothing abnormal was found.", params
    )
    assert "within normal limits" not in fixed.lower() or "require clinician review" in fixed.lower()
    assert "Glucose" in fixed


def test_consistent_summary_passes_through() -> None:
    params = [_param("Glucose", 180, "mg/dL", "High", "70-100")]
    summary = "Glucose is elevated and needs clinician review."
    assert ensure_consistent_summary(summary, params) == summary


def test_template_summary_counts_abnormals() -> None:
    summary = build_template_summary(SAMPLE_PARAMS)
    assert "require clinician review" in summary
    assert "Fasting Blood Glucose" in summary


# ── Legacy stored-report compatibility ─────────────────────────────────────

def test_legacy_risk_item_mapping() -> None:
    legacy = {"diabetes": {"level": "Moderate Risk", "reason": "Old reason."},
              "ckd": {"level": "Insufficient Data", "reason": "Old."}}
    item = legacy_risk_item("diabetes", legacy)
    assert item["state"] == STATE_ASSESSED  # historical label preserved as assessed
    assert item["level"] == "Moderate Risk"
    assert item["evidence"] == []
    empty = legacy_risk_item("anemia", {})
    assert empty["state"] == STATE_INSUFFICIENT_DATA
    assert empty["level"] is None
    modern = legacy_risk_item("ckd", {"ckd": {"state": "requires_review", "level": None,
                                              "reason": "R", "evidence": ["e"],
                                              "missing": ["m"], "method": "M",
                                              "guidance": "G"}})
    assert modern["state"] == STATE_REQUIRES_REVIEW
    assert modern["evidence"] == ["e"]


def test_legacy_item_validates_against_schema() -> None:
    item = DiseaseRiskItem(**legacy_risk_item("diabetes", {"diabetes": {"level": "Low Risk"}}))
    assert item.state == STATE_ASSESSED
    assert item.level == "Low Risk"


# ── LLM usage control ──────────────────────────────────────────────────────

REPORT_TEXT = (
    "COMPLETE BLOOD COUNT\n"
    "Hemoglobin: 10.2 g/dL (Reference Range: 12.0 - 15.5 g/dL)\n"
    "Serum Creatinine: 0.9 mg/dL 0.6-1.2\n"
)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["hf_space", "gemini", "ollama", "offline"])
async def test_llm_disabled_means_no_generation_calls(mode: str) -> None:
    """ENABLE_LLM_SUMMARY=false: deterministic result, zero provider calls."""
    mock_hf = MagicMock()
    mock_genai = MagicMock()
    mock_http = MagicMock()

    with patch("app.core.config.settings.AI_MODE", mode):
        with patch("app.core.config.settings.ENABLE_LLM_SUMMARY", False):
            with patch("app.services.hf_space_service.Client", return_value=mock_hf):
                with patch("app.services.gemini_service.genai", mock_genai):
                    with patch("app.services.ollama_service.httpx.AsyncClient", mock_http):
                        result = await analyse_report_text(REPORT_TEXT)

    assert result["parameters"], "deterministic pipeline must still produce rows"
    assert "clinician should verify" in result["summary"].lower()
    mock_hf.predict.assert_not_called()
    mock_genai.Client.assert_not_called()
    mock_http.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_quota_error_makes_exactly_one_call() -> None:
    mock_genai = MagicMock()
    mock_genai.Client.side_effect = Exception("429 RESOURCE_EXHAUSTED")
    with patch("app.core.config.settings.AI_MODE", "gemini"):
        with patch("app.core.config.settings.GEMINI_API_KEY", "k"):
            with patch("app.services.gemini_service.genai", mock_genai):
                with pytest.raises(HTTPException) as exc_info:
                    await analyse_report_text(REPORT_TEXT)
    assert exc_info.value.status_code == 503
    assert mock_genai.Client.call_count == 1


@pytest.mark.asyncio
async def test_each_provider_selected_independently() -> None:
    """hf_space selection still reaches HF; gemini key missing fails fast."""
    mock_hf = MagicMock()
    mock_hf.predict.return_value = (
        "### Overall Summary\nFine.\n\n"
        "#### Hemoglobin\n"
        "- **Test name**: Hemoglobin\n"
        "- **Reported value and unit**: 10.2 g/dL\n"
        "- **Reported reference range and unit**: 12.0 - 15.5 g/dL\n"
    )
    with patch("app.core.config.settings.AI_MODE", "hf_space"):
        with patch("app.services.hf_space_service.Client", return_value=mock_hf):
            result = await analyse_report_text(REPORT_TEXT)
    assert result["parameters"]
    mock_hf.predict.assert_called_once()

    with patch("app.core.config.settings.AI_MODE", "gemini"):
        with patch("app.core.config.settings.GEMINI_API_KEY", None):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text(REPORT_TEXT)
    assert exc_info.value.status_code == 503
