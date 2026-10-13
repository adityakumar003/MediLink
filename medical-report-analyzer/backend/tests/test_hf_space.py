"""Unit and integration tests for Hugging Face Space Qwen LLM analysis."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.hf_space_service import (
    _classify_numerical_status,
    _parse_numeric_value_and_range,
    _parse_qwen_markdown_response,
    analyse_report_text_hf,
)
from app.services.lab_validation import classify_lab_result
from app.services.ollama_service import analyse_report_text

MOCK_QWEN_OUTPUT = """### Test Analysis

#### Hemoglobin
- **Test name**: Hemoglobin
- **Reported value and unit**: 10.2 g/dL
- **Reported reference range and unit**: 12.0 - 15.5 g/dL
- **Classification**: BELOW RANGE
- **Explanation**: Hemoglobin carries oxygen in red blood cells. A low result indicates potential anemia.
- **Limitations/Uncertainty**: None noted

#### Fasting Blood Glucose
- **Test name**: Fasting Blood Glucose
- **Reported value and unit**: 110 mg/dL
- **Reported reference range and unit**: 70 - 99 mg/dL
- **Classification**: ABOVE RANGE
- **Explanation**: Fasting glucose measures blood sugar after fasting. Elevated levels may indicate prediabetes.
- **Limitations/Uncertainty**: None noted

#### Serum Creatinine
- **Test name**: Serum Creatinine
- **Reported value and unit**: 0.9 mg/dL
- **Reported reference range and unit**: 0.6 - 1.2 mg/dL
- **Classification**: WITHIN RANGE
- **Explanation**: Creatinine is a waste product filtered by kidneys. Normal level indicates healthy filtration.
- **Limitations/Uncertainty**: None noted

### Overall Summary
The report indicates mild anemia with a hemoglobin of 10.2 g/dL and borderline elevated fasting blood glucose of 110 mg/dL. Kidney function appears normal.

### Results Warranting Discussion
Hemoglobin below reference range and elevated fasting blood glucose should be reviewed by a clinician.

### Important Medical Reminder
Laboratory results must always be interpreted alongside clinical symptoms and medical history by a licensed physician.
"""

HEMOGLOBIN_REPORT = (
    "COMPLETE BLOOD COUNT\n"
    "Hemoglobin: 10.2 g/dL (Reference Range: 12.0 - 15.5 g/dL)\n"
    "Glucose: 110 mg/dL (Reference Range: 70 - 99 mg/dL)\n"
    "Serum Creatinine: 0.9 mg/dL 0.6-1.2\n"
)


# ── 1. Numerical & Reference Range Classification Tests ────────────────────

def test_hemoglobin_10_2_classified_as_below_range() -> None:
    """10.2 g/dL vs 12.0 - 15.5 g/dL is classified as Low (BELOW RANGE)."""
    val_num, lower, upper = _parse_numeric_value_and_range("10.2 g/dL", "12.0 - 15.5 g/dL")
    assert val_num == 10.2
    assert lower == 12.0
    assert upper == 15.5

    status = _classify_numerical_status(val_num, lower, upper, "WITHIN RANGE")
    assert status == "Low"
    assert classify_lab_result("10.2 g/dL", "12.0 - 15.5 g/dL", "NORMAL") == "Low"


def test_deterministic_range_boundaries() -> None:
    v1, l1, u1 = _parse_numeric_value_and_range("13.5", "12.0-15.5")
    assert _classify_numerical_status(v1, l1, u1, "WITHIN RANGE") == "Normal"

    v2, l2, u2 = _parse_numeric_value_and_range("220", "< 200")
    assert _classify_numerical_status(v2, l2, u2, "ABOVE RANGE") == "High"

    v3, l3, u3 = _parse_numeric_value_and_range("35", "> 40")
    assert _classify_numerical_status(v3, l3, u3, "BELOW RANGE") == "Low"


def test_missing_value_and_range_are_unknown() -> None:
    assert classify_lab_result("", "12.0 - 15.5 g/dL") == "Unknown"
    assert classify_lab_result("10.2 g/dL", "") == "Unknown"


def test_invalid_range_boundaries_are_unknown() -> None:
    assert classify_lab_result("10.2 g/dL", "15.5 - 12.0 g/dL") == "Unknown"


def test_unit_mismatch_is_unknown() -> None:
    assert classify_lab_result("10.2 g/dL", "12.0 - 15.5 mmol/L") == "Unknown"


def test_ocr_ambiguity_is_unknown() -> None:
    assert classify_lab_result("10.? g/dL", "12.0 - 15.5 g/dL") == "Unknown"
    assert classify_lab_result("~10.2 g/dL", "12.0-15.5 g/dL") == "Unknown"
    assert classify_lab_result("ill", "12.0 - 15.5 g/dL") == "Unknown"


def test_model_cannot_override_validated_status() -> None:
    assert classify_lab_result("10.2 g/dL", "12.0 - 15.5 g/dL", "WITHIN RANGE") == "Low"
    assert classify_lab_result("13.5 g/dL", "12.0 - 15.5 g/dL", "BELOW RANGE") == "Normal"


# ── 2. Response Parsing & Schema Contract Tests ────────────────────────────

def test_parse_qwen_markdown_response_schema() -> None:
    parsed = _parse_qwen_markdown_response(MOCK_QWEN_OUTPUT)

    assert "summary" in parsed
    assert "mild anemia" in parsed["summary"] or "10.2" in parsed["summary"]

    assert "parameters" in parsed
    assert len(parsed["parameters"]) == 3

    hb = next((p for p in parsed["parameters"] if "hemoglobin" in p["name"].lower()), None)
    assert hb is not None
    assert hb["value"] == 10.2
    assert hb["status"] == "Low"
    assert hb["unit"] == "g/dL"

    gl = next((p for p in parsed["parameters"] if "glucose" in p["name"].lower()), None)
    assert gl is not None
    assert gl["value"] == 110
    assert gl["status"] == "High"

    cr = next((p for p in parsed["parameters"] if "creatinine" in p["name"].lower()), None)
    assert cr is not None
    assert cr["value"] == 0.9
    assert cr["status"] == "Normal"

    risks = parsed["disease_risks"]
    assert risks["diabetes"]["level"] == "Moderate Risk"
    assert risks["anemia"]["level"] == "Moderate Risk"
    assert risks["ckd"]["level"] == "Low Risk"
    assert risks["cardiovascular"]["level"] == "Insufficient Data"


# ── 3. Empty & Short Input Error Handling ──────────────────────────────────

@pytest.mark.asyncio
async def test_empty_text_raises_clear_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await analyse_report_text_hf("")
    assert exc_info.value.status_code == 422
    assert "too short" in exc_info.value.detail.lower()

    with pytest.raises(HTTPException) as exc_info2:
        await analyse_report_text_hf("   short text   ")
    assert exc_info2.value.status_code == 422


# ── 4. Endpoint Failure & Timeout Error Handling ───────────────────────────

@pytest.mark.asyncio
async def test_hf_endpoint_timeout_handling() -> None:
    async def mock_timeout(fut, timeout):
        try:
            fut.close()
        except Exception:
            pass
        raise asyncio.TimeoutError()

    with patch("asyncio.wait_for", side_effect=mock_timeout):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 503
        assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_hf_endpoint_connection_error_handling() -> None:
    mock_client = MagicMock()
    mock_client.predict.side_effect = RuntimeError("Could not connect to Space host")

    with patch("app.services.hf_space_service.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 503
        assert "unavailable" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_hf_rate_limit_error_handling() -> None:
    mock_client = MagicMock()
    mock_client.predict.side_effect = RuntimeError("429 Too Many Requests: rate limit exceeded")

    with patch("app.services.hf_space_service.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 503
        assert "rate limit" in exc_info.value.detail.lower() or "quota" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_hf_auth_error_when_token_required() -> None:
    mock_client = MagicMock()
    mock_client.predict.side_effect = RuntimeError("401 Unauthorized: invalid token")

    with patch("app.services.hf_space_service.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 503
        assert "authentication" in exc_info.value.detail.lower() or "hf_token" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_hf_error_markdown_is_not_treated_as_analysis() -> None:
    mock_client = MagicMock()
    mock_client.predict.return_value = (
        "❌ **Model Initialization Error**: Unable to load `Qwen/Qwen2.5-3B-Instruct`."
    )

    with patch("app.services.hf_space_service.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_malformed_model_response_raises_502() -> None:
    mock_client = MagicMock()
    mock_client.predict.return_value = (
        "This is a long but unstructured paragraph with no laboratory parameter blocks."
    )

    with patch("app.services.hf_space_service.Client", return_value=mock_client):
        with pytest.raises(HTTPException) as exc_info:
            await analyse_report_text_hf("Sample medical report text with sufficient characters for testing.")
        assert exc_info.value.status_code == 502


# ── 5. Integration Router via analyse_report_text ──────────────────────────

@pytest.mark.asyncio
async def test_analyse_report_text_routes_to_hf_space() -> None:
    with patch("app.core.config.settings.AI_MODE", "hf_space"):
        with patch("app.services.hf_space_service.Client") as mock_client_cls:
            mock_instance = MagicMock()
            mock_instance.predict.return_value = MOCK_QWEN_OUTPUT
            mock_client_cls.return_value = mock_instance

            result = await analyse_report_text(HEMOGLOBIN_REPORT)

            assert "summary" in result
            hb = next(p for p in result["parameters"] if "hemoglobin" in p["name"].lower())
            assert hb["status"] == "Low"
            assert hb["value"] == 10.2
            mock_instance.predict.assert_called_once()
            kwargs = mock_instance.predict.call_args.kwargs
            assert kwargs["api_name"] == "/analyze"
            assert kwargs["max_new_tokens"] == 1024
            assert kwargs["temperature"] == 0.2
            assert kwargs["top_p"] == 0.9
            assert "Hemoglobin" in kwargs["report_text"] or "10.2" in kwargs["report_text"]
            mock_client_cls.assert_called_once()
            space_id = mock_client_cls.call_args.args[0]
            assert "MediBridge-qwen" in space_id or "adityaksingh" in space_id
