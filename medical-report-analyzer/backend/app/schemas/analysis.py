"""
app/schemas/analysis.py
────────────────────────
Pydantic schemas for the structured analysis result returned to the frontend.
All providers (Hugging Face Space, Ollama, offline) must map to this contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Any

from pydantic import BaseModel


class MedicalParameter(BaseModel):
    """A single extracted laboratory parameter from the report."""
    name: str
    value: Any                            # can be float or string
    unit: str
    status: str                           # "Normal" | "Low" | "High" | "Critical" | "Unknown"
    reference_range: Optional[str] = None
    report_flag: Optional[str] = None     # the report's own flag word, if printed
    flag_mismatch: bool = False           # True when the report flag disagrees with validated status


class DiseaseRiskItem(BaseModel):
    """Preliminary assessment for a single condition (decision support only)."""
    level: Optional[str] = None           # "Low Risk" etc. — only when state == "assessed"
    reason: str = ""
    state: str = "insufficient_data"      # assessed | insufficient_data | not_assessed | requires_review
    evidence: List[str] = []
    missing: List[str] = []
    method: Optional[str] = None
    guidance: str = ""


class DiseaseRisks(BaseModel):
    """Disease risk breakdown for the four supported conditions."""
    diabetes: DiseaseRiskItem
    ckd: DiseaseRiskItem
    anemia: DiseaseRiskItem
    cardiovascular: DiseaseRiskItem


class AnalysisResult(BaseModel):
    """
    Full analysis result returned by GET /analysis/{report_id}.
    """
    report_id: str
    summary: str
    parameters: List[MedicalParameter] = []
    disease_risks: DiseaseRisks
    analyzed_at: datetime


class AnalysisTriggerResponse(BaseModel):
    """Returned by POST /analysis/{report_id} after triggering analysis."""
    report_id: str
    status: str
    message: str
