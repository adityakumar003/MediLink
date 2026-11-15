"""
app/schemas/video.py
────────────────────
Pydantic schemas for video consultation lifecycle and LiveKit access tokens.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ConsultationCreateRequest(BaseModel):
    """Payload for POST /video/consultations."""

    patient_id: str = Field(min_length=1)
    scheduled_at: Optional[datetime] = Field(
        default=None,
        description="Future UTC timestamp. Omit to start an on-demand consultation now.",
    )


class VideoTokenRequest(BaseModel):
    """Payload for POST /video/token."""

    consultation_id: str = Field(min_length=1)


class ConsultationResponse(BaseModel):
    """A consultation as seen by one authenticated participant."""

    id: str
    room_name: str
    status: str
    patient_user_id: str
    patient_name: str
    doctor_user_id: str
    doctor_name: str
    doctor_specialization: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    created_at: datetime

    # Current viewer context and capabilities.
    role: Literal["patient", "doctor"]
    other_participant_id: str
    other_participant_name: str
    other_participant_role: Literal["patient", "doctor"]
    can_start: bool
    can_join: bool
    can_end: bool
    can_cancel: bool


class VideoTokenResponse(BaseModel):
    """Participant-specific LiveKit credentials and call display data."""

    token: str
    server_url: str
    room_name: str
    role: Literal["patient", "doctor"]
    participant_name: str
    other_participant_name: str
    other_participant_role: Literal["patient", "doctor"]
    consultation: ConsultationResponse
