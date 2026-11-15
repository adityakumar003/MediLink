"""
app/services/gemini_service.py
───────────────────────────────────
Google Gemini integration for MediBridge medical report analysis.

Independently selectable via AI_MODE=gemini. Shares the existing analysis
contract with the Hugging Face path: Gemini produces the same Markdown
template, which is parsed by the shared parser and validated
deterministically by lab_validation. The model explains; Python decides.

No calls are made unless AI_MODE=gemini. Failures raise, never fall back
to another provider.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict

from fastapi import HTTPException, status
from google import genai
from google.genai import types

from app.core.config import settings
from app.services.hf_space_service import (
    _parse_qwen_markdown_response as _parse_template_response,
)
from app.services.lab_validation import build_validated_context_block

logger = logging.getLogger(__name__)

# Aligned with ollama_service.analyse_report_text / hf_space_service.
MIN_TEXT_LENGTH: int = 50

# Concise output: full structured analysis fits comfortably here.
MAX_OUTPUT_TOKENS = 1024
TEMPERATURE = 0.2
TOP_P = 0.9

GEMINI_INSTRUCTIONS = """You are MediBridge, a cautious medical report explainer.
Rules:
- Use only the extracted report data, printed reference ranges, units, and provided context. Never invent values, ranges, symptoms, or diagnoses.
- A missing, ambiguous, or incompatible value or range means the result is unclassified — never guess a classification.
- Explain abnormalities cautiously. Do not diagnose diseases, invent causes, or recommend medication changes.
- End with exactly one concise doctor-facing summary paragraph of 50-70 words highlighting only the important abnormal findings, and a reminder that a qualified clinician must interpret the results.

Output format (follow exactly):

### Overall Summary
<the 50-70 word summary paragraph>

For each laboratory test found in the report:
#### <Test name>
- **Test name**: <name>
- **Reported value and unit**: <value and unit>
- **Reported reference range and unit**: <range and unit, or "Not provided">
- **Explanation**: <one brief sentence on its significance>
"""


def _http_exception_for_gemini_error(exc: Exception) -> HTTPException:
    """Map Gemini SDK failures to actionable errors without leaking the key."""
    message = str(exc)
    lowered = message.lower()
    logger.error("Gemini API error (%s): %s", type(exc).__name__, message[:300])

    if any(
        token in lowered
        for token in ("api key not valid", "invalid api key", "api_key_invalid", "401", "403", "permission denied")
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gemini API rejected the request (invalid API key). "
                "Set a valid GEMINI_API_KEY in the backend environment."
            ),
        )
    if "not_found" in lowered or "404" in lowered:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gemini API could not find the configured model. "
                "Check GEMINI_MODEL in the backend environment."
            ),
        )
    if any(
        token in lowered
        for token in ("high demand", "overloaded", "unavailable", "500", "503", "internal error")
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gemini API is temporarily overloaded. "
                "Please retry in a few minutes."
            ),
        )
    if any(
        token in lowered
        for token in ("429", "rate limit", "quota", "resource_exhausted", "too many requests")
    ):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gemini API rate limit or quota was reached. "
                "Please retry in a few minutes."
            ),
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Gemini AI service unavailable: {type(exc).__name__}",
    )


async def analyse_report_text_gemini(extracted_text: str) -> Dict[str, Any]:
    """
    Send extracted medical report text to Google Gemini and return the
    shared AnalysisResult-compatible dict (parameters re-validated in Python).
    """
    if not extracted_text or len(extracted_text.strip()) < MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Extracted text is too short to analyse. Please upload a valid medical report.",
        )

    if not re.search(r"\d", extracted_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No measurable laboratory values were found in the uploaded "
                "report. Please upload a lab report containing test results "
                "with numeric values."
            ),
        )

    api_key = settings.GEMINI_API_KEY if settings.GEMINI_API_KEY else None
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Gemini API key is not configured. "
                "Set GEMINI_API_KEY in the backend environment to use AI_MODE=gemini."
            ),
        )

    prompt_text = (
        GEMINI_INSTRUCTIONS
        + "\n\n"
        + build_validated_context_block(extracted_text)
    )
    model_name = settings.GEMINI_MODEL
    logger.info(
        "Dispatching medical analysis (%d chars) to Gemini model: %s",
        len(extracted_text),
        model_name,
    )

    def _call_gemini() -> str:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt_text,
            config=types.GenerateContentConfig(
                temperature=TEMPERATURE,
                top_p=TOP_P,
                max_output_tokens=MAX_OUTPUT_TOKENS,
            ),
        )
        return response.text or ""

    try:
        raw_output = await asyncio.wait_for(
            asyncio.to_thread(_call_gemini),
            timeout=settings.GEMINI_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Gemini API timed out after %.1f seconds.", settings.GEMINI_TIMEOUT_SECONDS
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Gemini API timed out after {settings.GEMINI_TIMEOUT_SECONDS}s. "
                "Please retry in a moment."
            ),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_exception_for_gemini_error(exc) from exc

    if not raw_output or not raw_output.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Gemini API returned empty response content.",
        )

    parsed = _parse_template_response(raw_output)
    if not parsed.get("parameters"):
        logger.warning(
            "Gemini response (%d chars) could not be mapped to laboratory parameters.",
            len(raw_output),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "AI returned an incomplete or unparseable analysis. "
                "Please try again; if it persists, check that the uploaded "
                "report is clear and readable."
            ),
        )

    logger.info("Received %d chars from Gemini model.", len(raw_output))
    return parsed
