"""
app/models/consultation.py
──────────────────────────
Beanie document model for real-time patient-doctor video consultations.

A consultation is the lifecycle record for one video room. The LiveKit room
itself is created lazily by LiveKit on the first participant join, so scheduling
a consultation never consumes room resources.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from beanie import Document, Indexed, Link
from pydantic import Field

from app.models.user import User
from app.utils.time_utils import utc_now


class ConsultationStatus(str, Enum):
    SCHEDULED = "scheduled"
    STARTED = "started"            # doctor has entered the room; patient may join
    IN_PROGRESS = "in_progress"    # patient has joined
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Consultation(Document):
    """Beanie document model for the consultations collection."""

    patient: Link[User]
    doctor: Link[User]
    room_name: Indexed(str, unique=True) = Field(  # type: ignore[valid-type]
        default_factory=lambda: f"medilink_{uuid4().hex}"
    )
    status: ConsultationStatus = ConsultationStatus.SCHEDULED
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    patient_joined_at: Optional[datetime] = None
    doctor_joined_at: Optional[datetime] = None
    patient_left_at: Optional[datetime] = None
    doctor_left_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Settings:
        name = "consultations"
        use_state_management = True
