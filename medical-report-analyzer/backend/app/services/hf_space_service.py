"""
app/services/hf_space_service.py
───────────────────────────────────
Hugging Face Space integration for MediBridge medical report analysis.
Invokes the deployed Qwen2.5-3B-Instruct Gradio Space on Hugging Face ZeroGPU:
    https://huggingface.co/spaces/adityaksingh/MediBridge-qwen

Responsibilities:
  - Connect to the Gradio Space using gradio_client.Client
  - Send extracted medical report text to the /analyze endpoint
  - Parse structured clinical explanations into the AnalysisResult schema
  - Apply deterministic numerical validation from lab_validation
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from gradio_client import Client

from app.core.config import settings
from app.services.lab_validation import (
    build_validated_context_block,
    classify_lab_result,
    classify_numerical_status as _classify_numerical_status,
    extract_unit,
    parse_numeric_value_and_range as _parse_numeric_value_and_range,
)

logger = logging.getLogger(__name__)

# Aligned with ollama_service.analyse_report_text
MIN_TEXT_LENGTH: int = 50

_SPACE_ERROR_MARKERS = (
    "❌",
    "⚠️",
    "model initialization error",
    "inference error",
    "no report text provided",
    "input too short",
    "no summary generated",
    "unable to load",
)


def _extract_space_id(space_url_or_id: str) -> str:
    """Extract the Hugging Face space repo ID from a URL or repo_id string."""
    cleaned = space_url_or_id.strip().rstrip("/")
    match = re.search(r"huggingface\.co/spaces/([^/]+/[^/]+)", cleaned)
    if match:
        return match.group(1)
    match_host = re.search(r"https?://([a-zA-Z0-9_-]+)\.hf\.space", cleaned)
    if match_host:
        return cleaned
    return cleaned


def _is_space_error_payload(raw_text: str) -> bool:
    stripped = (raw_text or "").strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    return any(marker in lowered or stripped.startswith(marker) for marker in _SPACE_ERROR_MARKERS)


def _http_exception_for_hf_error(exc: Exception, target_space: str) -> HTTPException:
    """Map Gradio/HTTP failures to actionable HTTP errors without leaking report text."""
    message = str(exc)
    lowered = message.lower()
    logger.error(
        "Hugging Face Space inference error (%s): %s: %s",
        target_space,
        type(exc).__name__,
        message[:300],
    )

    if any(token in lowered for token in ("401", "403", "unauthorized", "forbidden", "invalid token")):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Hugging Face Space ({target_space}) rejected the request (authentication). "
                "If the Space is private, set HF_TOKEN in the backend environment."
            ),
        )
    if any(token in lowered for token in ("429", "rate limit", "quota", "too many requests")):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Hugging Face Space ({target_space}) rate limit or quota was reached. "
                "Please retry in a few minutes."
            ),
        )
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Hugging Face AI Space ({target_space}) unavailable: {type(exc).__name__}",
    )


def _parse_value_and_unit(val_raw: str) -> tuple[Any, str]:
    val_parts = val_raw.split(maxsplit=1)
    raw_num = val_parts[0] if val_parts else val_raw
    unit = val_parts[1] if len(val_parts) > 1 else ""
    try:
        numeric_val: Any = float(raw_num) if "." in raw_num else int(raw_num)
    except ValueError:
        numeric_val = val_raw
    return numeric_val, unit


def _risk_from_status(
    param: Optional[Dict[str, Any]],
    *,
    missing_reason: str,
    high_reason: str,
    low_reason: str,
    normal_reason: str,
    high_level: str = "Moderate Risk",
    low_level: str = "Low Risk",
) -> Dict[str, str]:
    if param is None or param.get("status") == "Unknown":
        return {"level": "Insufficient Data", "reason": missing_reason}
    st = param["status"]
    val = param["value"]
    unit = param["unit"]
    name = param["name"]
    if st == "High":
        return {"level": high_level, "reason": high_reason.format(name=name, val=val, unit=unit)}
    if st == "Low":
        return {"level": low_level, "reason": low_reason.format(name=name, val=val, unit=unit)}
    if st == "Normal":
        return {"level": "Low Risk", "reason": normal_reason.format(name=name, val=val, unit=unit)}
    return {"level": "Insufficient Data", "reason": missing_reason}


def _parse_qwen_markdown_response(raw_text: str) -> Dict[str, Any]:
    """
    Parse Qwen markdown into the AnalysisResult schema.
    Parameter status is always reclassified by Python.
    """
    summary_match = re.search(r"###\s*Overall Summary\s*\n(.*?)(?=\n###|\Z)", raw_text, re.DOTALL)
    if summary_match and summary_match.group(1).strip():
        summary = summary_match.group(1).strip()
    else:
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip() and not p.startswith("#")]
        summary = paragraphs[0] if paragraphs else "Report analysis completed."

    parameters: List[Dict[str, Any]] = []
    seen_tests = set()
    test_blocks = re.split(r"(?:####|\*\*\*|\n\n- \*\*Test name\*\*:)", raw_text)

    for block in test_blocks:
        name_match = re.search(r"(?:-\s*)?\*\*Test name\*\*:\s*([^\n*]+)", block, re.IGNORECASE)
        val_match = re.search(r"(?:-\s*)?\*\*Reported value and unit\*\*:\s*([^\n*]+)", block, re.IGNORECASE)
        range_match = re.search(
            r"(?:-\s*)?\*\*Reported reference range and unit\*\*:\s*([^\n*]+)",
            block,
            re.IGNORECASE,
        )
        if not name_match or not val_match:
            continue

        name = name_match.group(1).strip()
        val_raw = val_match.group(1).strip()
        ref_range = range_match.group(1).strip() if range_match else ""
        name_key = name.lower()
        if name_key in seen_tests:
            continue
        seen_tests.add(name_key)

        numeric_val, unit = _parse_value_and_unit(val_raw)
        status_flag = classify_lab_result(val_raw, ref_range)

        parameters.append(
            {
                "name": name,
                "value": numeric_val,
                "unit": unit,
                "status": status_flag,
                "reference_range": ref_range or None,
            }
        )

    param_map = {p["name"].lower(): p for p in parameters}

    if not parameters:
        # The model sometimes abbreviates its answer (summary + consistency
        # checklist, or a Markdown table) instead of the full template.
        # Fall back to lenient formats before giving up with a 502.
        parameters = _parse_consistency_check_lines(raw_text)
        if not parameters:
            parameters = _parse_markdown_table_rows(raw_text)
        param_map = {p["name"].lower(): p for p in parameters}

    def find_param(*aliases: str) -> Optional[Dict[str, Any]]:
        for alias in aliases:
            for k, p in param_map.items():
                if alias.lower() in k:
                    return p
        return None

    glucose_p = find_param("glucose", "fpg", "blood sugar", "hba1c")
    renal_p = find_param("creatinine", "egfr", "bun", "urea", "uric acid")
    anemia_p = find_param("hemoglobin", "hb", "hematocrit", "rbc", "iron", "ferritin")
    cardio_p = find_param("cholesterol", "ldl", "triglyceride", "hdl", "blood pressure")

    diabetes_risk = _risk_from_status(
        glucose_p,
        missing_reason="No glucose or HbA1c tests found in the report.",
        high_reason="{name} ({val} {unit}) is above the reference range printed on the report.",
        low_reason="{name} ({val} {unit}) is below the reference range printed on the report.",
        normal_reason="{name} ({val} {unit}) is within the reference range printed on the report.",
    )
    ckd_risk = _risk_from_status(
        renal_p,
        missing_reason="No renal function indicators (e.g. Creatinine, eGFR, BUN) found in the report.",
        high_reason="{name} ({val} {unit}) is out of the reference range printed on the report.",
        low_reason="{name} ({val} {unit}) is out of the reference range printed on the report.",
        normal_reason="{name} ({val} {unit}) is within the reference range printed on the report.",
    )
    anemia_risk = _risk_from_status(
        anemia_p,
        missing_reason="No red blood cell or hemoglobin indicators found in the report.",
        high_reason="{name} ({val} {unit}) is above the reference range printed on the report.",
        low_reason="{name} ({val} {unit}) is below the reference range printed on the report.",
        normal_reason="{name} ({val} {unit}) is within the reference range printed on the report.",
        low_level="Moderate Risk",
    )
    cardio_risk = _risk_from_status(
        cardio_p,
        missing_reason="No lipid panel or cardiovascular indicators found in the report.",
        high_reason="{name} ({val} {unit}) is above the reference range printed on the report.",
        low_reason="{name} ({val} {unit}) is below the reference range printed on the report.",
        normal_reason="{name} ({val} {unit}) is within the expected limits printed on the report.",
    )

    return {
        "summary": summary,
        "parameters": parameters,
        "disease_risks": {
            "diabetes": diabetes_risk,
            "ckd": ckd_risk,
            "anemia": anemia_risk,
            "cardiovascular": cardio_risk,
        },
    }


def _parse_consistency_check_lines(raw_text: str) -> List[Dict[str, Any]]:
    """Fallback parser for `- Name: value unit (low - high unit)` summary lines.

    Used only when the primary `**Test name**` template yields no parameters
    (e.g. the model abbreviated its answer or the output was truncated).
    Status is still derived deterministically via :func:`classify_lab_result`.
    """
    parameters: List[Dict[str, Any]] = []
    seen: set[str] = set()
    pattern = re.compile(
        r"^-\s*(?P<name>[^:\n]{2,60}?):\s*"
        r"(?P<val>-?\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z/%^0-9.µu-]{0,20})"
        r"\s*\((?P<range>[^)\n]{1,80})\)",
        re.IGNORECASE | re.MULTILINE,
    )
    for match in pattern.finditer(raw_text):
        name = match.group("name").strip(" -*")
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        val_raw = match.group("val")
        unit = (match.group("unit") or "").strip()
        ref_range = match.group("range").strip()
        try:
            numeric_val: Any = float(val_raw) if "." in val_raw else int(val_raw)
        except ValueError:
            numeric_val = val_raw
        parameters.append(
            {
                "name": name,
                "value": numeric_val,
                "unit": unit,
                "status": classify_lab_result(f"{val_raw} {unit}".strip(), ref_range),
                "reference_range": ref_range or None,
            }
        )
    return parameters


def _parse_markdown_table_rows(raw_text: str) -> List[Dict[str, Any]]:
    """Fallback parser for `| Test | Value | Reference range | ... |` tables.

    Used only when the primary `**Test name**` template yields no parameters.
    Status is still derived deterministically via :func:`classify_lab_result`.
    """
    parameters: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not re.search(r"-?\d+(?:\.\d+)?", cells[1]):
            continue  # header or separator row
        name = re.sub(r"\*+", "", cells[0]).strip()
        key = name.lower()
        if not name or key in seen or "test" in key and "name" in key:
            continue
        seen.add(key)
        val_text = re.sub(r"\*+", "", cells[1]).strip()
        ref_range = re.sub(r"\*+", "", cells[2]).strip()
        num_match = re.search(r"-?\d+(?:\.\d+)?", val_text)
        if not num_match:
            continue
        raw_num = num_match.group(0)
        try:
            numeric_val: Any = float(raw_num) if "." in raw_num else int(raw_num)
        except ValueError:
            continue
        unit = extract_unit(val_text)
        parameters.append(
            {
                "name": name,
                "value": numeric_val,
                "unit": unit,
                "status": classify_lab_result(val_text, ref_range),
                "reference_range": ref_range or None,
            }
        )
    return parameters


async def analyse_report_text_hf(extracted_text: str) -> Dict[str, Any]:
    """
    Send extracted medical report text to the deployed Hugging Face Space
    serving Qwen2.5-3B-Instruct.
    """
    if not extracted_text or len(extracted_text.strip()) < MIN_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Extracted text is too short to analyse. Please upload a valid medical report.",
        )

    if not re.search(r"\d", extracted_text):
        # No measurable values at all (e.g. a prescription or letter rather
        # than a lab report): calling the LLM cannot produce parameters.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "No measurable laboratory values were found in the uploaded "
                "report. Please upload a lab report containing test results "
                "with numeric values."
            ),
        )

    target_space = _extract_space_id(settings.HF_SPACE_URL)
    token = settings.HF_TOKEN if settings.HF_TOKEN else None
    prompt_text = build_validated_context_block(extracted_text)

    logger.info(
        "Dispatching medical analysis (%d chars) to Hugging Face Space: %s",
        len(extracted_text),
        target_space,
    )

    def _call_hf_space() -> str:
        client = Client(target_space, token=token)
        result = client.predict(
            report_text=prompt_text,
            max_new_tokens=1024,
            temperature=0.2,
            top_p=0.9,
            api_name="/analyze",
        )
        return str(result)

    for attempt in (1, 2):
        try:
            raw_output = await asyncio.wait_for(
                asyncio.to_thread(_call_hf_space),
                timeout=settings.HF_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Hugging Face Space timed out after %.1f seconds.", settings.HF_TIMEOUT_SECONDS
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"Hugging Face Space ({target_space}) timed out after {settings.HF_TIMEOUT_SECONDS}s. "
                    "The ZeroGPU instance may be warming up. Please retry in a moment."
                ),
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise _http_exception_for_hf_error(exc, target_space) from exc

        if not raw_output or not raw_output.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Hugging Face Space returned empty response content.",
            )

        if _is_space_error_payload(raw_output):
            logger.error("Hugging Face Space returned an error payload (%d chars).", len(raw_output))
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Hugging Face Space returned an error instead of an analysis. "
                    "The model may still be loading. Please retry in a moment."
                ),
            )

        parsed = _parse_qwen_markdown_response(raw_output)
        if parsed.get("parameters"):
            logger.info("Received %d chars from Hugging Face Qwen model.", len(raw_output))
            return parsed

        # Non-empty but unparseable: formatting glitches are often transient,
        # so retry once before giving up with a 502.
        logger.warning(
            "Hugging Face response (%d chars) could not be mapped to laboratory "
            "parameters (attempt %d/2).",
            len(raw_output),
            attempt,
        )

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=(
            "AI returned an incomplete or unparseable analysis. "
            "Please try again; if it persists, check that the uploaded "
            "report is clear and readable."
        ),
    )
