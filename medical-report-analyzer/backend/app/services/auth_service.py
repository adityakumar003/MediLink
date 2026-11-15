"""
app/services/auth_service.py
─────────────────────────────
Authentication business logic: user registration, login, JWT creation.

Architecture: Routes → AuthService → Beanie models + security utilities
"""

from __future__ import annotations

import logging
import secrets
import string
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.security import hash_password, verify_password, create_access_token
from app.models.user import User, UserRole
from app.models.doctor_profile import DoctorProfile
from app.models.patient_profile import PatientProfile
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserInfo

logger = logging.getLogger(__name__)


def _generate_doctor_id() -> str:
    """Generate a unique doctor ID in format DR-XXXXXX (6 uppercase alphanumeric chars)."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"DR-{suffix}"


async def _ensure_unique_doctor_id() -> str:
    """Generate a doctor_id that does not already exist in the database."""
    for _ in range(10):  # max 10 attempts
        doctor_id = _generate_doctor_id()
        existing = await DoctorProfile.find_one(DoctorProfile.doctor_id == doctor_id)
        if existing is None:
            return doctor_id
    raise RuntimeError("Failed to generate a unique doctor ID after 10 attempts.")


async def register_user(payload: RegisterRequest) -> TokenResponse:
    """
    Create a new user account (patient or doctor).

    Steps:
      1. Check email uniqueness.
      2. Hash the password.
      3. Create User document.
      4. Create role-specific profile document.
      5. Return a JWT access token.
    """
    # 1. Check email uniqueness
    normalized_email = str(payload.email).strip().lower()
    existing = await User.find_one(User.email == normalized_email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Validate doctor fields
    if payload.role == UserRole.DOCTOR and not payload.specialization:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Doctors must provide a specialization.",
        )

    # 2. Hash password
    hashed = hash_password(payload.password)

    # 3. Create User document
    user = User(
        email=normalized_email,
        hashed_password=hashed,
        full_name=payload.full_name,
        role=payload.role,
    )
    await user.insert()

    # 4. Create profile. Remove the user if profile creation fails so
    # registration cannot leave an unusable account behind.
    try:
        if payload.role == UserRole.DOCTOR:
            doctor_id = await _ensure_unique_doctor_id()
            profile = DoctorProfile(
                user=user,
                doctor_id=doctor_id,
                specialization=payload.specialization or "General",
                experience=payload.experience or 0,
                hospital=payload.hospital,
                latitude=payload.latitude,
                longitude=payload.longitude,
            )
            await profile.insert()
            logger.info("Doctor registered: %s (doctor_id=%s)", user.email, doctor_id)
        else:
            profile = PatientProfile(
                user=user,
                age=payload.age,
                gender=payload.gender,
                phone=payload.phone,
            )
            await profile.insert()
            logger.info("Patient registered: %s", user.email)
    except Exception:
        await user.delete()
        raise

    # 5. Issue JWT
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )

    return TokenResponse(
        access_token=token,
        user=UserInfo(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            has_photo=user.profile_photo is not None,
        ),
    )


async def login_user(payload: LoginRequest) -> TokenResponse:
    """
    Authenticate an existing user with email and password.

    Returns a JWT access token on success.
    Raises HTTP 401 on invalid credentials.
    """
    normalized_email = str(payload.email).strip().lower()
    user = await User.find_one(User.email == normalized_email)

    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "email": user.email},
    )

    logger.info("User logged in: %s", user.email)

    return TokenResponse(
        access_token=token,
        user=UserInfo(
            id=str(user.id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            has_photo=user.profile_photo is not None,
        ),
    )


# ── Profile photo ─────────────────────────────────────────────────────────

PROFILE_PHOTO_DIRNAME = "profile_photos"
PROFILE_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png"}
PROFILE_PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/jpg"}
MAX_PROFILE_PHOTO_BYTES = 2 * 1024 * 1024


def _profile_photo_dir() -> Path:
    from app.core.config import settings

    path = Path(settings.UPLOAD_DIR) / PROFILE_PHOTO_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _photo_path(filename: str) -> Path:
    return _profile_photo_dir() / Path(filename).name


async def save_profile_photo(user: User, file: UploadFile) -> str:
    """
    Validate and store a profile photo for the authenticated user,
    replacing any previous one.

    Raises:
        HTTPException 400: invalid type, size, or unreadable image.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in PROFILE_PHOTO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo must be a JPG or PNG image.",
        )
    if (file.content_type or "").lower() not in PROFILE_PHOTO_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo must be a JPG or PNG image.",
        )

    content = await file.read()
    await file.seek(0)
    if len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile photo must be under 2 MB.",
        )

    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid image.",
        )

    if user.profile_photo:
        try:
            _photo_path(user.profile_photo).unlink(missing_ok=True)
        except OSError:
            pass

    stored = f"{uuid4().hex}{ext}"
    _photo_path(stored).write_bytes(content)
    user.profile_photo = stored
    await user.save()
    logger.info("Profile photo updated for %s", user.email)
    return stored


async def delete_profile_photo(user: User) -> None:
    """Remove the user's profile photo, reverting to default initials."""
    if user.profile_photo:
        try:
            _photo_path(user.profile_photo).unlink(missing_ok=True)
        except OSError:
            pass
        user.profile_photo = None
        await user.save()
