"""Unit tests for the optional Google Gemini analysis provider (all mocked)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.gemini_service import analyse_report_text_gemini
from app.services.ollama_service import analyse_report_text

MOCK_GEMINI_OUTPUT = """### Overall Summary
The report indicates mild anemia with hemoglobin below the reference range. Kidney function appears normal.

#### Hemoglobin
- **Test name**: Hemoglobin
- **Reported value and unit**: 10.2 g/dL
- **Reported reference range and unit**: 12.0 - 15.5 g/dL
- **Explanation**: Low hemoglobin may indicate anemia.

#### Serum Creatinine
- **Test name**: Serum Creatinine
- **Reported value and unit**: 0.9 mg/dL
- **Reported reference range and unit**: 0.6 - 1.2 mg/dL
- **Explanation**: Normal kidney filtration marker.
"""

REPORT_TEXT = (
    "COMPLETE BLOOD COUNT\n"
    "Hemoglobin: 10.2 g/dL (Reference Range: 12.0 - 15.5 g/dL)\n"
    "Serum Creatinine: 0.9 mg/dL 0.6-1.2\n"
)


def _mock_genai(text: str) -> MagicMock:
    mock_genai = MagicMock()
    mock_response = MagicMock()
    mock_response.text = text
    mock_genai.Client.return_value.models.generate_content.return_value = mock_response
    return mock_genai


# ── Dispatch ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_mode_routes_to_gemini_service() -> None:
    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)
    mock_hf_client = MagicMock()

    with patch("app.core.config.settings.AI_MODE", "gemini"):
        with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
            with patch("app.services.gemini_service.genai", mock_genai):
                with patch(
                    "app.services.hf_space_service.Client", return_value=mock_hf_client
                ):
                    result = await analyse_report_text(REPORT_TEXT)

    hb = next(p for p in result["parameters"] if "hemoglobin" in p["name"].lower())
    assert hb["value"] == 10.2
    assert hb["status"] == "Low"
    assert result["disease_risks"]["anemia"]["state"] == "requires_review"
    assert result["disease_risks"]["anemia"]["level"] is None
    mock_genai.Client.assert_called_once()
    mock_hf_client.predict.assert_not_called()


@pytest.mark.asyncio
async def test_hf_space_mode_does_not_call_gemini() -> None:
    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)
    mock_hf_client = MagicMock()
    mock_hf_client.predict.return_value = MOCK_GEMINI_OUTPUT

    with patch("app.core.config.settings.AI_MODE", "hf_space"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with patch(
                "app.services.hf_space_service.Client", return_value=mock_hf_client
            ):
                await analyse_report_text(REPORT_TEXT)

    mock_hf_client.predict.assert_called_once()
    mock_genai.Client.assert_not_called()


@pytest.mark.asyncio
async def test_offline_mode_does_not_call_gemini() -> None:
    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)

    with patch("app.core.config.settings.AI_MODE", "offline"):
        with patch("app.services.gemini_service.genai", mock_genai):
            result = await analyse_report_text(REPORT_TEXT)

    assert "summary" in result
    mock_genai.Client.assert_not_called()


# ── Success & schema ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_success_matches_analysis_schema() -> None:
    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)
    with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
        with patch("app.core.config.settings.GEMINI_MODEL", "test-model"):
            with patch("app.services.gemini_service.genai", mock_genai):
                result = await analyse_report_text_gemini(REPORT_TEXT)

    assert result["summary"]
    assert len(result["parameters"]) == 2
    cr = next(p for p in result["parameters"] if "creatinine" in p["name"].lower())
    assert cr["status"] == "Normal"
    assert set(result["disease_risks"]) == {"diabetes", "ckd", "anemia", "cardiovascular"}

    kwargs = mock_genai.Client.return_value.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "test-model"
    assert "Hemoglobin" in kwargs["contents"] or "10.2" in kwargs["contents"]


# ── Key, error, and malformed handling ─────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_missing_key_fails_without_sdk_call() -> None:
    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)
    with patch("app.core.config.settings.GEMINI_API_KEY", None):
        with patch("app.services.gemini_service.genai", mock_genai):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 503
    assert "GEMINI_API_KEY" in exc_info.value.detail
    mock_genai.Client.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_invalid_key_is_503() -> None:
    mock_genai = MagicMock()
    mock_genai.Client.side_effect = Exception("API key not valid. Please pass a valid API key.")

    with patch("app.core.config.settings.GEMINI_API_KEY", "bad-key"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 503
    assert "api key" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gemini_rate_limit_is_503() -> None:
    mock_genai = MagicMock()
    mock_genai.Client.side_effect = Exception("429 RESOURCE_EXHAUSTED: quota exceeded.")

    with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 503
    assert "rate limit" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gemini_timeout_is_503() -> None:
    async def mock_timeout(fut, timeout):
        try:
            fut.close()
        except Exception:
            pass
        raise asyncio.TimeoutError()

    mock_genai = _mock_genai(MOCK_GEMINI_OUTPUT)
    with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with patch("asyncio.wait_for", side_effect=mock_timeout):
                with pytest.raises(HTTPException) as exc_info:
                    await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 503
    assert "timed out" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_gemini_empty_response_is_502() -> None:
    mock_genai = _mock_genai("")
    with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_gemini_malformed_response_is_502() -> None:
    mock_genai = _mock_genai(
        "This is a long but unstructured paragraph with no laboratory parameter blocks."
    )
    with patch("app.core.config.settings.GEMINI_API_KEY", "test-key"):
        with patch("app.services.gemini_service.genai", mock_genai):
            with pytest.raises(HTTPException) as exc_info:
                await analyse_report_text_gemini(REPORT_TEXT)
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_gemini_short_input_is_422() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await analyse_report_text_gemini("too short")
    assert exc_info.value.status_code == 422
