"""
app/api/routes/video.py
───────────────────────
Authenticated video consultation lifecycle and LiveKit token endpoints.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_current_user, require_doctor_role
from app.models.user import User
from app.schemas.video import (
    ConsultationCreateRequest,
    ConsultationResponse,
    VideoTokenRequest,
    VideoTokenResponse,
)
from app.services import video_service

router = APIRouter()


@router.post(
    "/consultations",
    response_model=ConsultationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start now or schedule a video consultation (doctor only)",
)
async def create_consultation(
    payload: ConsultationCreateRequest,
    current_user: User = Depends(require_doctor_role),
) -> ConsultationResponse:
    """Create or start the single active consultation for an accepted patient."""
    return await video_service.create_consultation(
        current_user=current_user,
        patient_id=payload.patient_id,
        scheduled_at=payload.scheduled_at,
    )


@router.get(
    "/consultations",
    response_model=List[ConsultationResponse],
    summary="List my video consultations",
)
async def list_consultations(
    current_user: User = Depends(get_current_user),
) -> List[ConsultationResponse]:
    """Return the authenticated patient's or doctor's consultations."""
    return await video_service.list_consultations(current_user)


@router.get(
    "/consultations/{consultation_id}",
    response_model=ConsultationResponse,
    summary="Get one authorized consultation",
)
async def get_consultation(
    consultation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConsultationResponse:
    """Return a consultation only when the user is one of its participants."""
    return await video_service.get_consultation(consultation_id, current_user)


@router.post(
    "/consultations/{consultation_id}/start",
    response_model=ConsultationResponse,
    summary="Start a scheduled consultation (doctor only)",
)
async def start_consultation(
    consultation_id: str,
    current_user: User = Depends(require_doctor_role),
) -> ConsultationResponse:
    """Transition a scheduled consultation to started."""
    return await video_service.start_consultation(consultation_id, current_user)


@router.post(
    "/token",
    response_model=VideoTokenResponse,
    summary="Issue a LiveKit token for an authorized consultation participant",
)
async def create_video_token(
    payload: VideoTokenRequest,
    current_user: User = Depends(get_current_user),
) -> VideoTokenResponse:
    """Generate a participant-specific, room-scoped LiveKit access token."""
    return await video_service.issue_token(payload.consultation_id, current_user)


@router.post(
    "/consultations/{consultation_id}/leave",
    response_model=ConsultationResponse,
    summary="Record an intentional leave from a consultation",
)
async def leave_consultation(
    consultation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConsultationResponse:
    """Record an intentional leave without completing on temporary disconnects."""
    return await video_service.leave_consultation(consultation_id, current_user)


@router.post(
    "/consultations/{consultation_id}/end",
    response_model=ConsultationResponse,
    summary="End a consultation (doctor only)",
)
async def end_consultation(
    consultation_id: str,
    current_user: User = Depends(require_doctor_role),
) -> ConsultationResponse:
    """Complete an active consultation."""
    return await video_service.end_consultation(consultation_id, current_user)


@router.post(
    "/consultations/{consultation_id}/cancel",
    response_model=ConsultationResponse,
    summary="Cancel a scheduled or not-yet-joined consultation",
)
async def cancel_consultation(
    consultation_id: str,
    current_user: User = Depends(get_current_user),
) -> ConsultationResponse:
    """Cancel a consultation before both participants have joined."""
    return await video_service.cancel_consultation(consultation_id, current_user)
