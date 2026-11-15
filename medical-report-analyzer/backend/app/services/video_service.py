"""
app/services/video_service.py
─────────────────────────────
Business logic for LiveKit video consultations.

Architecture: Routes → VideoService → Beanie models / LiveKit AccessToken.

Rooms are not pre-created. LiveKit creates the room on the first authorized
participant join and automatically closes empty rooms, which keeps free-tier
usage low and avoids leaking rooms for cancelled or unused consultations.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from fastapi import HTTPException, status
from livekit import api

from app.core.config import settings
from app.models.consultation import Consultation, ConsultationStatus
from app.models.doctor_profile import DoctorProfile
from app.models.user import User, UserRole
from app.schemas.video import ConsultationResponse, VideoTokenResponse
from app.services.doctor_service import verify_patient_connection
from app.utils.link_utils import object_id, user_reference
from app.utils.time_utils import utc_now

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (ConsultationStatus.STARTED, ConsultationStatus.IN_PROGRESS)
CANCELLABLE_STATUSES = (ConsultationStatus.SCHEDULED, ConsultationStatus.STARTED)


def _role_value(user: User) -> str:
    return getattr(user.role, "value", user.role)


def _ensure_video_role(user: User) -> str:
    role = _role_value(user)
    if role not in {UserRole.PATIENT.value, UserRole.DOCTOR.value}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Video consultations are only available to patients and doctors.",
        )
    return role


def _normalize_future_datetime(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime and require it to be in the future."""
    scheduled = value
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=timezone.utc)
    scheduled = scheduled.astimezone(timezone.utc)
    if scheduled <= utc_now():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Scheduled consultation time must be in the future.",
        )
    return scheduled


def _require_livekit_configured() -> None:
    if not settings.livekit_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Video consultations are not configured on this server. "
                "Set LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET."
            ),
        )
    if not settings.LIVEKIT_URL.strip().lower().startswith(("ws://", "wss://")):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVEKIT_URL must be a ws:// or wss:// LiveKit server URL.",
        )


async def _get_consultation_or_404(consultation_id: str) -> Consultation:
    oid = object_id(consultation_id, "Consultation not found.")
    consultation = await Consultation.get(oid)
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found.")
    return consultation


async def _fetch_participants(consultation: Consultation) -> Tuple[User, User]:
    await consultation.fetch_link(Consultation.patient)
    await consultation.fetch_link(Consultation.doctor)

    patient = consultation.patient
    doctor = consultation.doctor
    if not isinstance(patient, User) or not isinstance(doctor, User):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Consultation participant data is incomplete.",
        )
    return patient, doctor


def _participant_context(
    consultation: Consultation,
    patient: User,
    doctor: User,
    current_user: User,
) -> tuple[str, User, str]:
    role = _ensure_video_role(current_user)
    current_user_id = str(current_user.id)

    if role == UserRole.PATIENT.value and current_user_id == str(patient.id):
        return role, doctor, UserRole.DOCTOR.value
    if role == UserRole.DOCTOR.value and current_user_id == str(doctor.id):
        return role, patient, UserRole.PATIENT.value

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You are not a participant in this consultation.",
    )


async def _to_response(
    consultation: Consultation,
    current_user: User,
) -> ConsultationResponse:
    patient, doctor = await _fetch_participants(consultation)
    role, other, other_role = _participant_context(consultation, patient, doctor, current_user)

    doctor_profile = await DoctorProfile.find_one(
        {"user": user_reference(doctor.id)},
    )

    can_join = consultation.status in ACTIVE_STATUSES
    can_start = role == UserRole.DOCTOR.value and consultation.status == ConsultationStatus.SCHEDULED
    can_end = role == UserRole.DOCTOR.value and consultation.status in ACTIVE_STATUSES
    can_cancel = consultation.status in CANCELLABLE_STATUSES

    return ConsultationResponse(
        id=str(consultation.id),
        room_name=consultation.room_name,
        status=consultation.status.value,
        patient_user_id=str(patient.id),
        patient_name=patient.full_name,
        doctor_user_id=str(doctor.id),
        doctor_name=doctor.full_name,
        doctor_specialization=doctor_profile.specialization if doctor_profile else None,
        scheduled_at=consultation.scheduled_at,
        started_at=consultation.started_at,
        ended_at=consultation.ended_at,
        created_at=consultation.created_at,
        role=role,  # type: ignore[arg-type]
        other_participant_id=str(other.id),
        other_participant_name=other.full_name,
        other_participant_role=other_role,  # type: ignore[arg-type]
        can_start=can_start,
        can_join=can_join,
        can_end=can_end,
        can_cancel=can_cancel,
    )


async def get_consultation(consultation_id: str, current_user: User) -> ConsultationResponse:
    """Return one consultation only if the current user participates in it."""
    consultation = await _get_consultation_or_404(consultation_id)
    return await _to_response(consultation, current_user)


async def list_consultations(current_user: User) -> List[ConsultationResponse]:
    """Return the current patient's or doctor's consultation history."""
    role = _ensure_video_role(current_user)
    if role == UserRole.PATIENT.value:
        query = {"patient": user_reference(current_user.id)}
    else:
        query = {"doctor": user_reference(current_user.id)}

    consultations = await (
        Consultation.find(query)
        .sort(-Consultation.created_at)
        .limit(100)
        .to_list()
    )
    return [await _to_response(consultation, current_user) for consultation in consultations]


async def _find_active_for_pair(
    patient_id: str,
    doctor_id: str,
) -> Consultation | None:
    return await Consultation.find_one(
        {
            "patient": user_reference(patient_id),
            "doctor": user_reference(doctor_id),
            "status": {
                "$in": [
                    ConsultationStatus.SCHEDULED,
                    ConsultationStatus.STARTED,
                    ConsultationStatus.IN_PROGRESS,
                ]
            },
        },
    )


async def create_consultation(
    current_user: User,
    patient_id: str,
    scheduled_at: datetime | None = None,
) -> ConsultationResponse:
    """
    Start an on-demand consultation, or schedule a future one.

    A doctor may only consult an accepted patient connection. There can be at
    most one active/scheduled consultation per patient-doctor pair.
    """
    role = _ensure_video_role(current_user)
    if role != UserRole.DOCTOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the doctor can initiate a video consultation.",
        )

    patient = await User.get(object_id(patient_id, "Patient not found."))
    if patient is None or not patient.is_active:
        raise HTTPException(status_code=404, detail="Patient not found.")
    if _role_value(patient) != UserRole.PATIENT.value:
        raise HTTPException(status_code=400, detail="The selected user is not a patient.")

    connected = await verify_patient_connection(str(current_user.id), str(patient.id))
    if not connected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Video consultations require an accepted doctor-patient connection.",
        )

    existing = await _find_active_for_pair(str(patient.id), str(current_user.id))

    if scheduled_at is not None:
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An active or scheduled consultation already exists for this patient.",
            )
        consultation = Consultation(
            patient=patient,
            doctor=current_user,
            status=ConsultationStatus.SCHEDULED,
            scheduled_at=_normalize_future_datetime(scheduled_at),
        )
        await consultation.insert()
        logger.info(
            "Doctor %s scheduled consultation %s for patient %s",
            current_user.id,
            consultation.id,
            patient.id,
        )
        return await _to_response(consultation, current_user)

    if existing is not None:
        if existing.status == ConsultationStatus.SCHEDULED:
            existing.status = ConsultationStatus.STARTED
            existing.started_at = utc_now()
            existing.updated_at = utc_now()
            await existing.save()
            logger.info("Doctor %s started scheduled consultation %s", current_user.id, existing.id)
        return await _to_response(existing, current_user)

    consultation = Consultation(
        patient=patient,
        doctor=current_user,
        status=ConsultationStatus.STARTED,
        started_at=utc_now(),
    )
    await consultation.insert()
    logger.info(
        "Doctor %s started consultation %s with patient %s",
        current_user.id,
        consultation.id,
        patient.id,
    )
    return await _to_response(consultation, current_user)


async def start_consultation(consultation_id: str, current_user: User) -> ConsultationResponse:
    """Move a scheduled consultation into the started state (doctor only)."""
    consultation = await _get_consultation_or_404(consultation_id)
    patient, doctor = await _fetch_participants(consultation)
    role, _, _ = _participant_context(consultation, patient, doctor, current_user)

    if role != UserRole.DOCTOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the doctor can start this consultation.",
        )
    if consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation is no longer active.",
        )
    if consultation.status == ConsultationStatus.SCHEDULED:
        consultation.status = ConsultationStatus.STARTED
        consultation.started_at = utc_now()
        consultation.updated_at = utc_now()
        await consultation.save()
        logger.info("Doctor %s started consultation %s", current_user.id, consultation.id)

    return await _to_response(consultation, current_user)


def _build_access_token(
    consultation: Consultation,
    participant: User,
    role: str,
) -> str:
    """Create a short-lived token scoped to exactly one consultation room."""
    access_token = (
        api.AccessToken(settings.LIVEKIT_API_KEY, settings.LIVEKIT_API_SECRET)
        .with_identity(str(participant.id))
        .with_name(participant.full_name)
        .with_metadata(json.dumps({
            "role": role,
            "consultation_id": str(consultation.id),
        }))
        .with_grants(api.VideoGrants(
            room_join=True,
            room=consultation.room_name,
            can_publish=True,
            can_subscribe=True,
            # Used only for in-room consultation-ended notifications.
            can_publish_data=True,
        ))
        .with_ttl(timedelta(minutes=settings.LIVEKIT_TOKEN_TTL_MINUTES))
    )
    return access_token.to_jwt()


async def issue_token(consultation_id: str, current_user: User) -> VideoTokenResponse:
    """
    Validate participation/state and issue participant-specific LiveKit credentials.

    The frontend never supplies a room name or participant identity; both are
    derived from the authenticated user and persisted consultation.
    """
    _require_livekit_configured()
    consultation = await _get_consultation_or_404(consultation_id)
    patient, doctor = await _fetch_participants(consultation)
    role, other, other_role = _participant_context(consultation, patient, doctor, current_user)

    if consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation is no longer active.",
        )

    if consultation.status == ConsultationStatus.SCHEDULED:
        if role != UserRole.DOCTOR.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The doctor has not started this consultation yet.",
            )
        consultation.status = ConsultationStatus.STARTED
        consultation.started_at = utc_now()

    now = utc_now()
    if role == UserRole.PATIENT.value:
        if consultation.status == ConsultationStatus.STARTED:
            consultation.status = ConsultationStatus.IN_PROGRESS
        consultation.patient_joined_at = now
        consultation.patient_left_at = None
    else:
        consultation.doctor_joined_at = now
        consultation.doctor_left_at = None

    consultation.updated_at = now
    await consultation.save()

    token = _build_access_token(consultation, current_user, role)
    logger.info(
        "Issued LiveKit token for consultation %s to %s %s",
        consultation.id,
        role,
        current_user.id,
    )
    response = await _to_response(consultation, current_user)

    return VideoTokenResponse(
        token=token,
        server_url=settings.LIVEKIT_URL.strip().rstrip("/"),
        room_name=consultation.room_name,
        role=role,  # type: ignore[arg-type]
        participant_name=current_user.full_name,
        other_participant_name=other.full_name,
        other_participant_role=other_role,  # type: ignore[arg-type]
        consultation=response,
    )


async def leave_consultation(consultation_id: str, current_user: User) -> ConsultationResponse:
    """
    Record an intentional leave. Temporary network disconnects do not call this.

    The consultation is completed only after both participants have explicitly
    left (or the doctor explicitly ends it).
    """
    consultation = await _get_consultation_or_404(consultation_id)
    patient, doctor = await _fetch_participants(consultation)
    role, _, _ = _participant_context(consultation, patient, doctor, current_user)

    if consultation.status in (ConsultationStatus.COMPLETED, ConsultationStatus.CANCELLED):
        return await _to_response(consultation, current_user)
    if consultation.status == ConsultationStatus.SCHEDULED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation has not started yet.",
        )

    now = utc_now()
    if role == UserRole.PATIENT.value:
        consultation.patient_left_at = now
    else:
        consultation.doctor_left_at = now

    if consultation.patient_left_at and consultation.doctor_left_at:
        consultation.status = ConsultationStatus.COMPLETED
        consultation.ended_at = now

    consultation.updated_at = now
    await consultation.save()
    logger.info("Consultation %s: %s left", consultation.id, role)
    return await _to_response(consultation, current_user)


async def end_consultation(consultation_id: str, current_user: User) -> ConsultationResponse:
    """Doctor-only explicit end action, which completes the consultation."""
    consultation = await _get_consultation_or_404(consultation_id)
    patient, doctor = await _fetch_participants(consultation)
    role, _, _ = _participant_context(consultation, patient, doctor, current_user)

    if role != UserRole.DOCTOR.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the doctor can end this consultation.",
        )
    if consultation.status == ConsultationStatus.COMPLETED:
        return await _to_response(consultation, current_user)
    if consultation.status in (ConsultationStatus.SCHEDULED, ConsultationStatus.CANCELLED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consultation has not started or is already cancelled.",
        )

    now = utc_now()
    consultation.status = ConsultationStatus.COMPLETED
    consultation.ended_at = now
    consultation.doctor_left_at = consultation.doctor_left_at or now
    consultation.updated_at = now
    await consultation.save()
    logger.info("Doctor %s ended consultation %s", current_user.id, consultation.id)
    return await _to_response(consultation, current_user)


async def cancel_consultation(consultation_id: str, current_user: User) -> ConsultationResponse:
    """Cancel a scheduled or started (not yet in-progress) consultation."""
    consultation = await _get_consultation_or_404(consultation_id)
    patient, doctor = await _fetch_participants(consultation)
    _participant_context(consultation, patient, doctor, current_user)

    if consultation.status == ConsultationStatus.CANCELLED:
        return await _to_response(consultation, current_user)
    if consultation.status not in CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a scheduled or not-yet-joined consultation can be cancelled.",
        )

    now = utc_now()
    consultation.status = ConsultationStatus.CANCELLED
    consultation.cancelled_at = now
    consultation.updated_at = now
    await consultation.save()
    logger.info("Consultation %s cancelled by %s", consultation.id, current_user.id)
    return await _to_response(consultation, current_user)
